import pytest
from sqlalchemy import select
from app.models import *
from app.services import platforms
from app.services.athlete_ids import public_athlete_id
from tests.test_competition_teams import create_coach_team, login, ok, prepare
from tests.test_integrations import finished
from tests.test_ministry import ministry_login
from tests.test_workflows import open_comp


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


def codeforces(rows, phase="FINISHED"):
    return {
        "status": "OK",
        "result": {
            "contest": {"id": 2050, "name": "Codeforces Round 990", "phase": phase},
            "rows": [
                {"party": {"members": [{"handle": h} for h in handles], **extra},
                 "rank": rank, "points": points}
                for handles, rank, points, extra in rows
            ],
        },
    }


@pytest.fixture()
def remote(monkeypatch):
    """Replaces the network: url -> response, every request is recorded."""
    answers, calls = {}, []

    def get(url, params, headers):
        calls.append((url, params, headers))
        answer = answers[url]
        return answer(params) if callable(answer) else answer

    monkeypatch.setattr(platforms, "get", get)
    monkeypatch.setattr(platforms, "check_url", lambda url, lookup=False: None)
    return answers, calls


CF = "https://codeforces.com/api/contest.standings"


def two_participants(client, h, users):
    """Closed competition with the demo athlete and athlete1 approved."""
    comp = open_comp(client, h["admin"])
    other, other_id = login(client, "athlete1")
    for headers, aid in ((h["athlete"], users["athlete"]["athlete_id"]), (other, other_id)):
        app_id = ok(client.post(
            f"/api/competitions/{comp['id']}/applications", headers=headers, json={"athlete_id": aid}
        ), 201)["id"]
        ok(client.patch(f"/api/applications/{app_id}", headers=h["admin"], json={"status": "approved"}))
    ok(client.patch(f"/api/competitions/{comp['id']}/state", headers=h["admin"], json={"state": "closed"}))
    return comp, users["athlete"]["athlete_id"], other, other_id


def profile(client, headers, aid, platform_logins):
    current = ok(client.get(f"/api/athletes/{aid}", headers=headers))
    body = {
        "full_name": current["full_name"],
        "organization_id": current["organization_id"],
        "municipality": current["municipality"],
        "training_stage": current["training_stage"],
        "disciplines": [
            {k: d[k] for k in ("discipline_id", "start_year", "end_year")}
            for d in current["disciplines"]
        ],
        "platform_logins": platform_logins,
    }
    return client.put(f"/api/athletes/{aid}", headers=headers, json=body)


def test_profile_logins_are_unique_and_private(env):
    client, factory, h, users = env
    aid = users["athlete"]["athlete_id"]
    res = profile(client, h["athlete"], aid, {"codeforces": " Tourist ", "ctfd": "pwn"})
    assert res.status_code == 200, res.text
    assert res.json()["platform_logins"] == {"codeforces": "Tourist", "ctfd": "pwn"}
    # a missing key keeps the login, an empty one removes it
    res = profile(client, h["athlete"], aid, {"ctfd": ""})
    assert res.json()["platform_logins"] == {"codeforces": "Tourist"}

    other, other_id = login(client, "athlete1")
    res = profile(client, other, other_id, {"codeforces": "tourist"})
    assert res.status_code == 409 and "уже привязан" in res.text
    assert profile(client, other, other_id, {"codeforces": "x" * 101}).status_code == 422

    ministry = ministry_login(client)
    item = next(a for a in client.get("/api/athletes", headers=ministry).json() if a["id"] == aid)
    assert "platform_logins" not in item


def test_codeforces_standings_matched_and_published(env, remote):
    client, factory, h, users = env
    answers, calls = remote
    comp, aid, other, other_id = two_participants(client, h, users)
    ok(profile(client, h["athlete"], aid, {"codeforces": "Petr"}))
    url = f"/api/competitions/{comp['id']}/results/platform"
    answers[CF] = Response(codeforces([
        (["tourist"], 1, 3000, {}),       # not from the region
        (["petr"], 2, 2500, {}),
        (["stranger"], 3, 2500, {}),
        (["ghost"], 3, 2000, {}),
    ]))

    res = client.post(url, headers=h["admin"], json={"platform": "codeforces", "contest": "2050"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert calls[0][1] == {"contestId": "2050"}
    # a participant without a login does not block the protocol
    assert body["ready"] and body["dry_run"]
    assert [r["athlete_id"] for r in body["rows"]] == [public_athlete_id(aid)]
    assert [m["athlete_id"] for m in body["matched"]] == [public_athlete_id(aid)]
    assert [(m["id"], m["in_protocol"]) for m in body["missing"]] == [(other_id, False)]
    assert {u["login"] for u in body["unmatched"]} == {"tourist", "stranger", "ghost"}
    assert body["source"]["title"] == "Codeforces Round 990"

    # binding by hand: only an approved participant, not someone else's login
    bad = client.post(url, headers=h["admin"], json={
        "platform": "codeforces", "contest": "2050", "bindings": {"ghost": 999}})
    assert bad.status_code == 422
    bad = client.post(url, headers=h["admin"], json={
        "platform": "codeforces", "contest": "2050", "bindings": {"petr": other_id}})
    assert bad.status_code == 409

    payload = {"platform": "codeforces", "contest": "2050", "bindings": {"ghost": other_id}}
    res = client.post(url, headers=h["admin"], json=payload)
    body = res.json()
    assert body["ready"] and body["mode"] == "publication"
    # places are recounted among the participants: 2 -> 1, 3 -> 2
    assert [(m["platform_place"], m["place"]) for m in body["matched"]] == [(2, 1), (3, 2)]
    assert [r["athlete_id"] for r in body["rows"]] == [public_athlete_id(aid), public_athlete_id(other_id)]

    res = client.post(url, headers=h["admin"], json={**payload, "dry_run": False})
    assert res.status_code == 200, res.text
    assert res.json()["version"] == 1
    detail = client.get(f"/api/competitions/{comp['id']}", headers=h["admin"]).json()
    assert detail["state"] == "published"
    assert detail["results_source"]["contest"] == "2050"
    assert ok(client.get(f"/api/athletes/{other_id}", headers=other))["platform_logins"] == {
        "codeforces": "ghost"
    }
    with factory() as db:
        entry = db.scalars(
            select(AuditLog).where(AuditLog.action == "Импорт результатов с площадки")
        ).one()
        assert entry.details["bound_logins"] == {"ghost": other_id}

    # a correction needs a reason; the bound login now matches by itself
    del payload["bindings"]
    answers[CF] = Response(codeforces([(["petr"], 2, 2600, {}), (["ghost"], 3, 2000, {})]))
    res = client.post(url, headers=h["admin"], json={**payload, "dry_run": False})
    assert res.status_code == 422 and "основание" in res.text
    res = client.post(url, headers=h["admin"],
                      json={**payload, "dry_run": False, "reason": "Перепроверка решений"})
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "correction" and res.json()["version"] == 2


def test_protocol_of_found_participants_only(env, remote):
    client, factory, h, users = env
    answers, _ = remote
    comp, aid, other, other_id = two_participants(client, h, users)
    ok(profile(client, h["athlete"], aid, {"codeforces": "petr"}))
    url = f"/api/competitions/{comp['id']}/results/platform"
    answers[CF] = Response(codeforces([(["tourist"], 1, 30, {}), (["petr"], 2, 25, {}),
                                       (["ghost"], 3, 20, {})]))
    body = ok(client.post(url, headers=h["admin"],
                          json={"platform": "codeforces", "contest": "7", "dry_run": False}))
    assert body["version"] == 1 and body["count"] == 1
    with factory() as db:
        results = db.scalars(
            select(CompetitionResult).where(CompetitionResult.competition_id == comp["id"])
        ).all()
        assert [(r.athlete_id, r.place, r.score) for r in results] == [(aid, 1, 25)]

    # a correction adds a participant found later and keeps the others
    payload = {"platform": "codeforces", "contest": "7", "reason": "Найден логин участника"}
    body = ok(client.post(url, headers=h["admin"],
                          json={**payload, "bindings": {"ghost": other_id}, "dry_run": False}))
    assert body["mode"] == "correction" and body["version"] == 2 and body["changed"] == 1
    protocol = client.get(f"/api/competitions/{comp['id']}", headers=h["admin"]).json()["results"]
    assert [(r["athlete_id"], r["place"]) for r in protocol] == [(aid, 1), (other_id, 2)]

    # rows of the published protocol are kept: a participant in it must be found
    answers[CF] = Response(codeforces([(["ghost"], 3, 21, {})]))
    body = ok(client.post(url, headers=h["admin"], json=payload))
    assert not body["ready"] and "уже в протоколе" in body["conflicts"][0]
    res = client.post(url, headers=h["admin"], json={**payload, "dry_run": False})
    assert res.status_code == 422 and "уже в протоколе" in res.text


def test_shared_places_and_fsp_ids(env, remote):
    client, factory, h, users = env
    answers, _ = remote
    comp, aid, _, other_id = two_participants(client, h, users)
    answers[CF] = Response(codeforces([
        ([public_athlete_id(aid)], 4, 10, {}),
        ([public_athlete_id(other_id).lower()], 4, 10, {}),
    ]))
    body = ok(client.post(f"/api/competitions/{comp['id']}/results/platform", headers=h["admin"],
                          json={"platform": "codeforces", "contest": "1"}))
    assert body["ready"] and [m["place"] for m in body["matched"]] == [1, 1]


def test_platform_errors(env, remote):
    client, factory, h, users = env
    answers, _ = remote
    comp, aid, _ = finished(client, h, users)
    url = f"/api/competitions/{comp['id']}/results/platform"

    def post(**body):
        return client.post(url, headers=h["admin"], json={"platform": "codeforces", "contest": "1", **body})

    assert post(contest="abc").status_code == 422
    answers[CF] = Response({"status": "FAILED", "comment": "contestId: Contest with id 1 not found"}, 400)
    res = post()
    assert res.status_code == 422 and "not found" in res.text
    answers[CF] = Response(codeforces([], phase="CODING"))
    assert "ещё не завершён" in post().text
    answers[CF] = Response(codeforces([]))
    assert "пуста" in post().text
    answers[CF] = Response(None, 503)
    assert post().status_code == 502

    def offline(params):
        raise platforms.httpx.ConnectError("down")

    answers[CF] = offline
    assert post().status_code == 502
    # Yandex Contest needs a token
    assert "OAuth" in post(platform="yandex_contest").text
    for role in ("athlete", "coach", "judge"):
        assert client.post(url, headers=h[role], json={"platform": "codeforces", "contest": "1"}).status_code == 403


def test_ctfd_refuses_internal_address(env, monkeypatch):
    client, factory, h, users = env
    comp, aid, _ = finished(client, h, users)
    monkeypatch.setattr(platforms.settings, "webhook_allow_private", False)
    for contest in ("http://127.0.0.1:8000", "http://localhost", "ftp://ctf.example.org", "ctf"):
        res = client.post(f"/api/competitions/{comp['id']}/results/platform", headers=h["admin"],
                          json={"platform": "ctfd", "contest": contest})
        assert res.status_code == 422, contest


def test_yandex_contest_pages(env, remote, monkeypatch):
    client, factory, h, users = env
    answers, calls = remote
    comp, aid, _ = finished(client, h, users)
    ok(profile(client, h["athlete"], aid, {"yandex_contest": "orenburg-coder"}))
    monkeypatch.setattr(platforms, "YANDEX_PAGE", 2)
    base = f"{platforms.YANDEX_API}/contests/77"
    answers[base] = Response({"name": "Отборочный тур"})
    pages = {
        1: [{"participantInfo": {"login": "a", "name": "A"}, "placeFrom": 1, "score": "5"},
            {"participantInfo": {"login": "b", "name": "B"}, "placeFrom": 2, "score": "4"}],
        2: [{"participantInfo": {"login": "Orenburg-Coder", "name": "Я"}, "placeFrom": 3, "score": "3,5"}],
    }
    answers[base + "/standings"] = lambda params: Response({"rows": pages[params["page"]]})
    body = ok(client.post(f"/api/competitions/{comp['id']}/results/platform", headers=h["admin"],
                          json={"platform": "yandex_contest", "contest": "77", "token": "y0_secret"}))
    assert body["ready"] and body["matched"][0]["score"] == 3.5 and body["matched"][0]["place"] == 1
    assert body["source"]["title"] == "Отборочный тур"
    assert all(c[2]["Authorization"] == "OAuth y0_secret" for c in calls)
    assert "y0_secret" not in str(body)


def test_ctfd_team_competition(env, remote):
    client, factory, h, users, base, people = prepare(env)
    answers, calls = remote
    team, url = create_coach_team(client, h, base, people)
    for headers, _ in people[:2]:
        ok(client.patch(url + "/response", headers=headers, json={"status": "accepted"}))
    ok(client.post(url + "/submit", headers=h["coach"]))
    ok(client.patch(url + "/review", headers=h["admin"], json={"status": "approved"}))
    ok(client.patch(base + "/state", headers=h["admin"], json={"state": "closed"}))
    ok(profile(client, people[1][0], people[1][1], {"ctfd": "n0p"}))
    answers["https://ctf.example.org/api/v1/scoreboard"] = Response({"success": True, "data": [
        {"pos": 1, "name": "MSU", "score": 900, "members": [{"name": "x"}]},
        {"pos": 2, "name": "Команда мечты", "score": 700, "members": [{"name": "n0p"}, {"name": "y"}]},
    ]})
    body = ok(client.post(base + "/results/platform", headers=h["admin"],
                          json={"platform": "ctfd", "contest": "https://ctf.example.org/",
                                "token": "ctfd_abc", "dry_run": False}))
    assert body["version"] == 1 and body["matched"][0]["team_id"] == team["id"]
    assert calls[0][2]["Authorization"] == "Token ctfd_abc"
    with factory() as db:
        results = db.scalars(
            select(CompetitionResult).where(CompetitionResult.competition_id == team["competition_id"])
        ).all()
        assert {(r.place, r.score, r.team_name) for r in results} == {(1, 700, "ОренКод")}


def test_codeforces_gym_request_is_signed(env, remote, monkeypatch):
    client, factory, h, users = env
    answers, calls = remote
    comp, aid, _ = finished(client, h, users)
    monkeypatch.setattr(platforms.settings, "codeforces_api_key", "key")
    monkeypatch.setattr(platforms.settings, "codeforces_api_secret", "secret")
    answers[CF] = Response(codeforces([([public_athlete_id(aid)], 1, 5, {})]))
    body = ok(client.post(f"/api/competitions/{comp['id']}/results/platform", headers=h["admin"],
                          json={"platform": "codeforces", "contest": "100001"}))
    assert body["ready"] and body["source"]["url"].endswith("/gym/100001/standings")
    params = calls[0][1]
    assert params["apiKey"] == "key" and len(params["apiSig"]) == 6 + 128
