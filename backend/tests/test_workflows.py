from datetime import date, timedelta
from io import BytesIO
from zipfile import ZipFile
import pytest
from sqlalchemy import select
from app.models import *
from app.services.ratings import recalculate
from app.services.notifications import deliver, deadlines


def competition(client, h, **overrides):
    today = date.today().isoformat()
    payload = dict(
        title="Тестовый турнир",
        discipline_id=1,
        type_id=1,
        start_date=today,
        end_date=today,
        deadline=today,
        location="Демо-арена",
        format="onsite",
        status="regional",
        min_age=0,
        max_age=100,
        calendar_plan="Оренбургская область",
        calendar_number="TEST-1",
    )
    payload.update(overrides)
    res = client.post("/api/competitions", headers=h, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def open_comp(client, h, **overrides):
    comp = competition(client, h, **overrides)
    res = client.patch(
        f"/api/competitions/{comp['id']}/state", headers=h, json={"state": "open"}
    )
    assert res.status_code == 200, res.text
    return comp


def test_full_competition_workflow(env):
    client, factory, h, users = env
    c = open_comp(client, h["admin"])
    cid = c["id"]
    aid = users["athlete"]["athlete_id"]
    assigned = client.post(
        f"/api/competitions/{cid}/judges",
        headers=h["admin"],
        json={"judge_id": users["judge"]["judge_id"], "position": "Главный судья"},
    )
    assert assigned.status_code == 201, assigned.text
    body = {"athlete_id": aid}
    application = client.post(
        f"/api/competitions/{cid}/applications", headers=h["athlete"], json=body
    )
    assert application.status_code == 201, application.text
    assert (
        client.post(
            f"/api/competitions/{cid}/applications", headers=h["athlete"], json=body
        ).status_code
        == 409
    )
    apid = application.json()["id"]
    assert (
        client.patch(
            f"/api/applications/{apid}", headers=h["admin"], json={"status": "approved"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/applications/{apid}", headers=h["admin"], json={"status": "rejected"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/competitions/{cid}/state",
            headers=h["admin"],
            json={"state": "closed"},
        ).status_code
        == 200
    )
    result = client.post(
        f"/api/competitions/{cid}/results",
        headers=h["admin"],
        json={"results": [{"athlete_id": aid, "place": 1, "score": 980}]},
    )
    assert result.status_code == 200, result.text
    assert (
        client.post(
            f"/api/competitions/{cid}/results",
            headers=h["admin"],
            json={"results": [{"athlete_id": aid, "place": 1, "score": 900}]},
        ).status_code
        == 409
    )
    history = client.get("/api/results", headers=h["athlete"]).json()
    assert any(r["competition_id"] == cid for r in history)
    rating = client.get(
        f"/api/ratings?season={date.today().year}&discipline_id=1", headers=h["athlete"]
    ).json()
    own = next(r for r in rating if r["athlete_id"] == aid)
    assert own["points"] == 168 and own["coefficient"] == 1.2
    for fmt in ["pdf", "docx", "xlsx"]:
        export = client.get(f"/api/exports/protocol/{cid}.{fmt}", headers=h["athlete"])
        assert export.status_code == 200, export.text
        if fmt == "pdf":
            assert export.content.startswith(b"%PDF")
        else:
            archive = ZipFile(BytesIO(export.content))
            assert "[Content_Types].xml" in archive.namelist()
    assert (
        client.put(
            "/api/team",
            headers=h["admin"],
            json={
                "season": date.today().year,
                "discipline_id": 1,
                "athlete_ids": [aid],
            },
        ).status_code
        == 200
    )
    assert (
        client.get("/api/exports/team.docx?order=true", headers=h["admin"]).status_code
        == 200
    )
    notices = client.get("/api/notifications", headers=h["athlete"]).json()
    assert any(n["event_key"] == f"protocol:{cid}:{aid}" for n in notices)


@pytest.mark.parametrize("role", ["athlete", "coach", "judge"])
def test_rbac_prevents_admin_actions(env, role):
    client, _, h, u = env
    assert client.post("/api/competitions", headers=h[role], json={}).status_code in [
        403,
        422,
    ]
    assert client.get("/api/audit", headers=h[role]).status_code == 403
    assert client.get("/api/reports/population", headers=h[role]).status_code == 403
    # Same multi-role JWT, but active athlete role: admin privileges must not leak.
    switched = {**h["admin"], "X-Active-Role": role}
    assert client.get("/api/users", headers=switched).status_code == 403


def test_unassigned_role_and_expired_token(env):
    client, _, h, u = env
    assert (
        client.get(
            "/api/users", headers={**h["athlete"], "X-Active-Role": "admin"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer broken"}
        ).status_code
        == 401
    )
    assert client.get("/api/athletes/2", headers=h["athlete"]).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"consent": False},
        {"guardian_consent": False},
        {"role": "admin"},
        {"birth_date": "2099-01-01"},
    ],
)
def test_registration_consent_validation(env, changes):
    client, *_ = env
    data = {
        "email": "minor@example.com",
        "password": "safe-pass-2026",
        "full_name": "Демо Несовершеннолетний",
        "birth_date": date(date.today().year - 15, 1, 1).isoformat(),
        "role": "athlete",
        "consent": True,
        "guardian_name": "Демо Представитель",
        "guardian_consent": True,
    }
    data.update(changes)
    assert client.post("/api/auth/register", json=data).status_code == 422


def test_registration_and_profile(env):
    client, _, h, _ = env
    data = {
        "email": "new-athlete@example.com",
        "password": "safe-pass-2026",
        "full_name": "Демо Новый Спортсмен",
        "birth_date": "2001-05-12",
        "consent": True,
    }
    res = client.post("/api/auth/register", json=data)
    assert res.status_code == 201, res.text
    user = res.json()["user"]
    assert user["consent_at"] and user["roles"] == ["athlete"]
    assert client.post("/api/auth/register", json=data).status_code == 409
    headers = {
        "Authorization": "Bearer " + res.json()["access_token"],
        "X-Active-Role": "athlete",
    }
    profile = {
        "full_name": data["full_name"],
        "municipality": "Орск",
        "disciplines": [{"discipline_id": 6, "start_year": 2024}],
    }
    result = client.put(
        "/api/athletes/" + str(user["athlete_id"]), headers=headers, json=profile
    )
    assert result.status_code == 200, result.text
    assert result.json()["disciplines"][0]["discipline_id"] == 6


def test_coach_consent_and_discipline_scope(env):
    client, _, h, u = env
    aid = u["athlete"]["athlete_id"]
    comp = open_comp(client, h["admin"])
    url = f"/api/competitions/{comp['id']}/applications"
    assert (
        client.post(url, headers=h["coach"], json={"athlete_id": aid}).status_code
        == 403
    )
    link = client.post(
        "/api/links", headers=h["coach"], json={"athlete_id": aid, "discipline_id": 1}
    )
    assert link.status_code == 201, link.text
    lid = link.json()["id"]
    assert (
        client.patch(
            f"/api/links/{lid}", headers=h["coach"], json={"status": "active"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/links/{lid}", headers=h["athlete"], json={"status": "active"}
        ).status_code
        == 200
    )
    assert (
        client.post(url, headers=h["coach"], json={"athlete_id": aid}).status_code
        == 201
    )
    assert (
        client.patch(
            f"/api/links/{lid}", headers=h["athlete"], json={"status": "ended"}
        ).status_code
        == 200
    )
    other = open_comp(client, h["admin"], title="Второй турнир")
    assert (
        client.post(
            f"/api/competitions/{other['id']}/applications",
            headers=h["coach"],
            json={"athlete_id": aid},
        ).status_code
        == 403
    )
    assert len(client.get("/api/links", headers=h["athlete"]).json()[0]["history"]) == 3


def test_age_deadlines_and_complete_protocol(env):
    client, _, h, u = env
    aid = u["athlete"]["athlete_id"]
    comp = open_comp(client, h["admin"], min_age=30, max_age=40)
    assert (
        client.post(
            f"/api/competitions/{comp['id']}/applications",
            headers=h["athlete"],
            json={"athlete_id": aid},
        ).status_code
        == 422
    )
    comp = open_comp(client, h["admin"])
    res = client.post(
        f"/api/competitions/{comp['id']}/applications",
        headers=h["athlete"],
        json={"athlete_id": aid},
    )
    client.patch(
        f"/api/applications/{res.json()['id']}",
        headers=h["admin"],
        json={"status": "approved"},
    )
    client.patch(
        f"/api/competitions/{comp['id']}/state",
        headers=h["admin"],
        json={"state": "closed"},
    )
    assert (
        client.post(
            f"/api/competitions/{comp['id']}/results",
            headers=h["admin"],
            json={"results": [{"athlete_id": aid, "place": 2, "score": 10}]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/competitions/{comp['id']}/applications",
            headers=h["athlete"],
            json={"athlete_id": aid},
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/exports/protocol/{comp['id']}.pdf", headers=h["admin"]
        ).status_code
        == 409
    )


def test_rank_and_judge_category_decisions(env):
    client, _, h, u = env
    result = client.get("/api/results", headers=h["athlete"]).json()[0]
    res = client.post(
        "/api/rank-applications",
        headers=h["athlete"],
        json={
            "athlete_id": u["athlete"]["athlete_id"],
            "result_id": result["id"],
            "name": "II",
        },
    )
    assert res.status_code == 201, res.text
    decision = {
        "status": "approved",
        "assigned_on": date.today().isoformat(),
        "expires_on": (date.today() + timedelta(days=365)).isoformat(),
        "order_number": "TEST-26",
    }
    assert (
        client.patch(
            "/api/rank-applications/" + str(res.json()["id"]),
            headers=h["admin"],
            json=decision,
        ).status_code
        == 200
    )
    ranks = client.get("/api/ranks", headers=h["athlete"]).json()["sports"]
    assert any(r["name"] == "II" and r["result_id"] == result["id"] for r in ranks)
    res = client.post(
        "/api/rank-applications",
        headers=h["judge"],
        json={"name": "Судья первой категории", "kind": "confirmation"},
    )
    assert res.status_code == 201, res.text
    assert (
        client.patch(
            "/api/rank-applications/" + str(res.json()["id"]),
            headers=h["admin"],
            json=decision,
        ).status_code
        == 200
    )
    assert any(
        c["name"] == "Судья первой категории"
        for c in client.get("/api/ranks", headers=h["judge"]).json()["categories"]
    )


def test_suspension_rating_rules_and_population(env):
    client, _, h, u = env
    aid = u["athlete"]["athlete_id"]
    year = date.today().year
    assert (
        client.put(
            "/api/athletes/" + str(aid) + "/suspension",
            headers=h["admin"],
            json={
                "suspended_until": (date.today() + timedelta(days=2)).isoformat(),
                "reason": "Тестовое отстранение",
            },
        ).status_code
        == 200
    )
    assert all(
        r["athlete_id"] != aid
        for r in client.get(f"/api/ratings?season={year}", headers=h["admin"]).json()
    )
    assert (
        client.put(
            "/api/team",
            headers=h["admin"],
            json={"season": year, "discipline_id": 1, "athlete_ids": [aid]},
        ).status_code
        == 422
    )
    client.put(
        "/api/athletes/" + str(aid) + "/suspension",
        headers=h["admin"],
        json={"suspended_until": None, "reason": "Снятие ограничения"},
    )
    assert (
        client.put(
            "/api/rating-rules/regional",
            headers=h["admin"],
            json={"first": 50, "second": 35, "third": 25},
        ).status_code
        == 200
    )
    r = next(
        r
        for r in client.get(
            f"/api/ratings?season={year}&discipline_id=1", headers=h["admin"]
        ).json()
        if r["athlete_id"] == aid
    )
    assert r["points"] == 132
    report = client.get("/api/reports/population", headers=h["admin"])
    assert report.status_code == 200 and len(report.json()["totals"]) == 2
    assert report.json()["totals"][-1]["count"] == 19
    assert (
        client.get("/api/exports/population.xlsx", headers=h["admin"]).status_code
        == 200
    )


def test_notifications_deadlines_idempotent_and_ownership(env, monkeypatch):
    client, factory, h, u = env
    with factory() as db:
        deadlines(db)
        db.commit()
        before = len(db.scalars(select(Notification)).all())
        deadlines(db)
        db.commit()
        assert len(db.scalars(select(Notification)).all()) == before
    notices = client.get("/api/notifications", headers=h["athlete"]).json()
    assert notices
    nid = notices[0]["id"]
    assert (
        client.patch(f"/api/notifications/{nid}/read", headers=h["judge"]).status_code
        == 403
    )
    assert (
        client.patch(f"/api/notifications/{nid}/read", headers=h["athlete"]).status_code
        == 200
    )


def test_foreign_keys_and_sql_constraints(env):
    from sqlalchemy.exc import IntegrityError

    _, factory, _, _ = env
    with factory() as db:
        db.add(AthleteDiscipline(athlete_id=999999, discipline_id=1, start_year=2026))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_actual_smtp_delivery_to_local_capture(env, monkeypatch):
    import socketserver
    import threading
    from email import message_from_bytes
    from app.config import settings

    received = []

    class SMTPHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 localhost test SMTP\r\n")
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                command = line.split(b" ")[0].strip().upper()
                if command in (b"EHLO", b"HELO"):
                    self.wfile.write(b"250-localhost\r\n250 SIZE 1000000\r\n")
                elif command == b"DATA":
                    self.wfile.write(b"354 Send message\r\n")
                    body = []
                    while True:
                        part = self.rfile.readline()
                        if part in (b".\r\n", b""):
                            break
                        body.append(part)
                    received.append(b"".join(body))
                    self.wfile.write(b"250 Accepted\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 OK\r\n")

    server = socketserver.TCPServer(("127.0.0.1", 0), SMTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", server.server_address[1])
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_tls", False)
    try:
        _, factory, _, _ = env
        with factory() as db:
            deliver(db)
            notices = db.scalars(select(Notification)).all()
            assert all(n.mailed_at and not n.last_error for n in notices)
        assert received
        assert message_from_bytes(received[0])["To"].endswith("@demo.example")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_demo_minors_have_guardian_consent(env):
    from app.services.common import age_at

    _, factory, _, _ = env
    with factory() as db:
        for user in db.scalars(select(User)):
            assert user.consent_at and user.consent_version
            if age_at(user.birth_date) < 18:
                assert user.guardian_name and user.guardian_consent_at


def test_notifications_respect_active_role(env):
    client, factory, h, users = env
    with factory() as db:
        notice = Notification(
            user_id=users["admin"]["id"],
            title="Внутренняя заявка",
            body="Только федерации",
            event_key="application:999999",
        )
        db.add(notice)
        db.commit()
        nid = notice.id
    assert any(
        n["id"] == nid
        for n in client.get("/api/notifications", headers=h["admin"]).json()
    )
    switched = {**h["admin"], "X-Active-Role": "athlete"}
    assert all(
        n["id"] != nid
        for n in client.get("/api/notifications", headers=switched).json()
    )
    assert (
        client.patch(f"/api/notifications/{nid}/read", headers=switched).status_code
        == 403
    )


def test_regulation_upload_and_download(env):
    client, factory, h, users = env
    comp = competition(client, h["admin"])
    url = f"/api/competitions/{comp['id']}/regulation"
    pdf = b"%PDF-1.4\n% demo regulation\n%%EOF"

    def upload(name, content):
        return client.put(
            url, headers=h["admin"], files={"file": (name, content, "text/plain")}
        )

    assert upload("polozhenie.txt", b"hello").status_code == 422
    assert upload("fake.pdf", b"PK\x03\x04zip").status_code == 422
    assert upload("big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024)).status_code == 413
    assert (
        client.put(
            url, headers=h["athlete"], files={"file": ("a.pdf", pdf)}
        ).status_code
        == 403
    )
    res = upload("C:\\docs\\Положение турнира.pdf", pdf)
    assert res.status_code == 200, res.text
    assert res.json()["filename"] == "Положение турнира.pdf"
    assert client.get(url, headers=h["athlete"]).status_code == 404
    client.patch(
        f"/api/competitions/{comp['id']}/state",
        headers=h["admin"],
        json={"state": "open"},
    )
    detail = client.get(f"/api/competitions/{comp['id']}", headers=h["athlete"])
    assert detail.json()["regulation_file"]["size"] == len(pdf)
    file = client.get(url, headers=h["athlete"])
    assert file.status_code == 200
    assert file.content == pdf
    assert file.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in file.headers["content-disposition"]
    assert client.delete(url, headers=h["admin"]).status_code == 204
    assert client.get(url, headers=h["athlete"]).status_code == 404
    assert (
        client.get(f"/api/competitions/{comp['id']}", headers=h["athlete"]).json()[
            "regulation_file"
        ]
        is None
    )


def test_demo_competitions_have_regulation(env):
    client, factory, h, users = env
    comps = client.get("/api/competitions?state=open", headers=h["athlete"]).json()
    comp = next(c for c in comps if c["regulation_file"])
    file = client.get(f"/api/competitions/{comp['id']}/regulation", headers=h["athlete"])
    assert file.status_code == 200 and file.content.startswith(b"%PDF-")


def test_age_groups_eligibility_and_hint(env):
    client, factory, h, u = env
    aid = u["athlete"]["athlete_id"]
    groups = {
        g["name"]: g
        for g in client.get("/api/age-groups", headers=h["athlete"]).json()
    }
    assert {"Юноши", "Девушки", "Мужчины", "Женщины"} <= set(groups)
    # Demo athlete is female and turns 17 this year.
    comp = open_comp(
        client,
        h["admin"],
        age_group_ids=[groups["Юноши"]["id"], groups["Девушки"]["id"]],
    )
    assert (comp["min_age"], comp["max_age"]) == (14, 17)
    view = client.get(f"/api/competitions/{comp['id']}", headers=h["athlete"]).json()
    assert view["eligible"] is True
    assert [g["name"] for g in view["age_check"]["groups"]] == ["Девушки"]
    hint = client.get(
        f"/api/competitions/{comp['id']}/eligibility",
        headers=h["athlete"],
        params={"athlete_id": aid},
    ).json()
    assert hint["eligible"] and hint["year_age"] == 17
    res = client.post(
        f"/api/competitions/{comp['id']}/applications",
        headers=h["athlete"],
        json={"athlete_id": aid},
    )
    assert res.status_code == 201, res.text
    assert res.json()["age_group_id"] == groups["Девушки"]["id"]
    detail = client.get(f"/api/competitions/{comp['id']}", headers=h["admin"]).json()
    assert detail["applications"][0]["age_group"] == "Девушки"

    # Only boys: age fits, sex does not; without sex the athlete is asked to fill it.
    boys = open_comp(client, h["admin"], age_group_ids=[groups["Юноши"]["id"]])
    view = client.get(f"/api/competitions/{boys['id']}", headers=h["athlete"]).json()
    assert view["age_check"]["reason"] == "sex" and view["eligible"] is False
    with factory() as db:
        db.get(User, u["athlete"]["id"]).sex = None
        db.commit()
    res = client.post(
        f"/api/competitions/{boys['id']}/applications",
        headers=h["athlete"],
        json={"athlete_id": aid},
    )
    assert res.status_code == 422 and "пол" in res.json()["detail"]

    adults = open_comp(client, h["admin"], age_group_ids=[groups["Женщины"]["id"]])
    view = client.get(f"/api/competitions/{adults['id']}", headers=h["athlete"]).json()
    assert view["age_check"]["reason"] == "age"
    listed = client.get(
        "/api/competitions", headers=h["athlete"], params={"eligible": True}
    ).json()
    assert adults["id"] not in {c["id"] for c in listed}


def test_age_group_directory_management(env):
    client, _, h, _users = env
    payload = dict(
        name="Мальчики", sex="male", min_age=10, max_age=13, age_rule="start"
    )
    assert (
        client.post("/api/age-groups", headers=h["athlete"], json=payload).status_code
        == 403
    )
    bad = client.post(
        "/api/age-groups", headers=h["admin"], json={**payload, "min_age": 15}
    )
    assert bad.status_code == 422
    group = client.post("/api/age-groups", headers=h["admin"], json=payload).json()
    other = client.post(
        "/api/age-groups", headers=h["admin"], json={**payload, "discipline_id": 2}
    ).json()
    comp = competition(client, h["admin"], age_group_ids=[group["id"]])
    payload_comp = {
        k: comp[k]
        for k in [
            "title", "discipline_id", "type_id", "start_date", "end_date",
            "deadline", "location", "format", "status", "calendar_plan",
            "calendar_number",
        ]
    }
    res = client.post(
        "/api/competitions",
        headers=h["admin"],
        json={**payload_comp, "age_group_ids": [other["id"]]},
    )
    assert res.status_code == 422
    assert (
        client.put(
            f"/api/age-groups/{group['id']}",
            headers=h["admin"],
            json={**payload, "max_age": 12},
        ).status_code
        == 200
    )
    assert (
        client.delete(f"/api/age-groups/{group['id']}", headers=h["admin"]).status_code
        == 409
    )
    client.patch(
        f"/api/competitions/{comp['id']}/state", headers=h["admin"], json={"state": "open"}
    )
    assert (
        client.put(
            f"/api/age-groups/{group['id']}", headers=h["admin"], json=payload
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/api/age-groups/{other['id']}", headers=h["admin"]).status_code
        == 204
    )


def test_profile_sex(env):
    client, _, h, u = env
    aid = u["athlete"]["athlete_id"]
    profile = client.get(f"/api/athletes/{aid}", headers=h["athlete"]).json()
    assert profile["sex"] == "female"
    body = {
        k: profile[k]
        for k in ["full_name", "organization_id", "municipality", "training_stage"]
    }
    body["disciplines"] = [
        {k: d[k] for k in ["discipline_id", "start_year", "end_year"]}
        for d in profile["disciplines"]
    ]
    res = client.put(f"/api/athletes/{aid}", headers=h["athlete"], json=body)
    assert res.json()["sex"] == "female"
    res = client.put(
        f"/api/athletes/{aid}", headers=h["athlete"], json={**body, "sex": "male"}
    )
    assert res.json()["sex"] == "male"
    assert client.get("/api/auth/me", headers=h["athlete"]).json()["sex"] == "male"


@pytest.mark.parametrize(
    "status, type_id, level",
    [
        ("regional", 2, "regional"),
        ("interregional", 1, "interregional"),
        ("national", 1, "russian_championship"),
        ("national", 3, "russian_championship"),
        ("national", 2, "russian_junior"),
        ("national", 4, "interregional"),
    ],
)
def test_rating_level_from_status_and_type(env, status, type_id, level):
    client, _, h, _ = env
    plan = "Оренбургская область" if status == "regional" else "ЕКП"
    comp = competition(
        client, h["admin"], status=status, type_id=type_id, calendar_plan=plan
    )
    assert comp["status"] == status and comp["rating_level"] == level
    meta = client.get("/api/metadata", headers=h["admin"]).json()
    assert meta["rating_levels"][status][str(type_id)] == level


def test_rating_level_follows_edit_and_new_type(env):
    client, _, h, _ = env
    assert (
        client.post(
            "/api/competitions",
            headers=h["admin"],
            json={"status": "national", "calendar_plan": "Оренбургская область"},
        ).status_code
        == 422
    )
    res = client.post(
        "/api/competition-types",
        headers=h["admin"],
        json={"name": "Всероссийская спартакиада", "rating_class": "junior"},
    )
    assert res.status_code == 201 and res.json()["rating_class"] == "junior"
    assert (
        client.post(
            "/api/competition-types",
            headers=h["admin"],
            json={"name": "Неизвестный", "rating_class": "elite"},
        ).status_code
        == 422
    )
    comp = competition(client, h["admin"])
    assert comp["rating_level"] == "regional"
    body = {
        k: comp[k]
        for k in [
            "title", "discipline_id", "start_date", "end_date", "deadline",
            "location", "format", "calendar_number",
        ]
    }
    res = client.put(
        f"/api/competitions/{comp['id']}",
        headers=h["admin"],
        json={
            **body,
            "type_id": res.json()["id"],
            "status": "national",
            "calendar_plan": "ЕКП",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["rating_level"] == "russian_junior"
