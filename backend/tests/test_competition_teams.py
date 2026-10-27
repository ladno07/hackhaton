from datetime import date, timedelta
import pytest
from sqlalchemy import select
from app.models import (
    Athlete,
    AthleteDiscipline,
    Competition,
    CompetitionApplication,
    CompetitionTeamMember,
    ProtocolVersion,
    AuditLog,
)
from test_workflows import open_comp


def login(client, email):
    client.cookies.clear()  # independent athlete browsers in this workflow
    response = client.post(
        "/api/auth/login",
        json={"email": email + "@demo.example", "password": "DemoPass2026!"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    client.cookies.clear()
    return {
        "Authorization": "Bearer " + data["access_token"],
        "X-Active-Role": "athlete",
    }, data["user"]["athlete_id"]


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def prepare(env, rating=False):
    client, factory, h, users = env
    first, aid1 = login(client, "athlete1")
    second, aid2 = login(client, "athlete2")
    third, aid3 = login(client, "athlete3")
    comp = open_comp(
        client,
        h["admin"],
        entry_mode="team",
        team_min=2,
        team_max=3,
        team_rating=rating,
    )
    base = f"/api/competitions/{comp['id']}"
    return (
        client,
        factory,
        h,
        users,
        base,
        [(first, aid1), (second, aid2), (third, aid3)],
    )


def create_coach_team(client, h, base, people, name="ОренКод"):
    team = ok(
        client.post(
            base + "/teams",
            headers=h["coach"],
            json={"name": name, "captain_id": people[0][1]},
        ),
        201,
    )
    url = base + f"/teams/{team['id']}"
    ok(
        client.post(
            url + "/members", headers=h["coach"], json={"athlete_id": people[1][1]}
        ),
        201,
    )
    return team, url


@pytest.mark.parametrize("rating", [False, True])
def test_team_full_workflow_results_exports_and_rating(env, rating):
    client, factory, h, users, base, people = prepare(env, rating)
    team, url = create_coach_team(client, h, base, people)
    assert all(
        m["status"] == "invited"
        for m in ok(client.get(base + "/teams", headers=h["coach"]))[0]["members"]
    )
    assert client.post(url + "/submit", headers=h["coach"]).status_code == 422
    assert (
        client.patch(
            url + "/response", headers=h["coach"], json={"status": "accepted"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            url + "/response", headers=h["athlete"], json={"status": "accepted"}
        ).status_code
        == 403
    )
    for headers, _ in people[:2]:
        ok(
            client.patch(
                url + "/response", headers=headers, json={"status": "accepted"}
            )
        )
    assert client.get(base + "/teams", headers=h["athlete"]).json() == []
    ok(client.post(url + "/submit", headers=h["coach"]))
    assert ok(client.get("/api/dashboard", headers=h["admin"]))["applications"] >= 1
    assert (
        client.patch(
            url + "/review", headers=people[0][0], json={"status": "approved"}
        ).status_code
        == 403
    )
    ok(client.patch(url + "/review", headers=h["admin"], json={"status": "approved"}))
    assert (
        client.delete(url + f"/members/{people[1][1]}", headers=h["coach"]).status_code
        == 409
    )
    assert (
        client.put(
            url,
            headers=h["coach"],
            json={"name": "Другой состав", "captain_id": people[0][1]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + "/applications",
            headers=people[0][0],
            json={"athlete_id": people[0][1]},
        ).status_code
        == 409
    )
    apps = ok(client.get(base, headers=h["admin"]))["applications"]
    assert {a["athlete_id"] for a in apps if a["status"] == "approved"} == {
        p[1] for p in people[:2]
    }
    assert (
        client.patch(
            f"/api/applications/{apps[0]['id']}",
            headers=h["admin"],
            json={"status": "rejected"},
        ).status_code
        == 409
    )
    ok(client.patch(base + "/state", headers=h["admin"], json={"state": "closed"}))
    assert (
        client.post(
            base + "/results",
            headers=h["admin"],
            json={
                "results": [
                    {
                        "athlete_id": people[0][1],
                        "place": 1,
                        "score": 99,
                        "team_name": "Подмена",
                    }
                ]
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            base + "/results",
            headers=h["admin"],
            json={"team_results": [{"team_id": 999999, "place": 1, "score": 99}]},
        ).status_code
        == 422
    )
    body = {"team_results": [{"team_id": team["id"], "place": 1, "score": 100}]}
    ok(client.post(base + "/results", headers=h["admin"], json=body))
    comp = ok(client.get(base, headers=people[0][0]))
    assert len(comp["results"]) == 2
    assert all(
        (r["team_name"], r["place"], r["score"]) == ("ОренКод", 1, 100)
        for r in comp["results"]
    )
    assert (
        client.get(
            f"/api/exports/protocol/{comp['id']}.xlsx", headers=people[0][0]
        ).status_code
        == 200
    )
    for headers, aid in people[:2]:
        assert any(
            r["competition_id"] == comp["id"]
            for r in client.get("/api/results", headers=headers).json()
        )
        summary = ok(
            client.get(f"/api/coaching/athletes/{aid}/summary", headers=h["coach"])
        )
        assert any(
            r["competition_id"] == comp["id"] and r["team_name"] == "ОренКод"
            for r in summary["results"]
        )
    rankings = ok(
        client.get(
            f"/api/ratings?season={date.today().year}&discipline_id=1",
            headers=h["admin"],
        )
    )
    for _, aid in people[:2]:
        counted = any(
            b["competition_id"] == comp["id"]
            for r in rankings
            if r["athlete_id"] == aid
            for b in r["breakdown"]
        )
        assert counted == rating
    body["team_results"][0]["score"] = 105
    ok(
        client.put(
            base + "/results",
            headers=h["admin"],
            json={**body, "reason": "Уточнение баллов команды"},
        )
    )
    assert (
        client.post(
            url + "/reopen", headers=h["coach"], json={"reason": "Замена участника"}
        ).status_code
        == 409
    )
    versions = ok(client.get(base + "/protocol-versions", headers=h["admin"]))
    assert len(versions) == 2
    assert all(
        r["score"] == 105 for r in ok(client.get(base, headers=h["admin"]))["results"]
    )
    with factory() as db:
        assert (
            len(
                db.scalars(
                    select(ProtocolVersion).where(
                        ProtocolVersion.competition_id == comp["id"]
                    )
                ).all()
            )
            == 2
        )
        assert db.scalar(
            select(AuditLog.id).where(AuditLog.action == "Решение по командной заявке")
        )
    notices = ok(client.get("/api/notifications", headers=people[0][0]))
    assert any(n["event_key"].startswith("competition-team:") for n in notices)


def test_athlete_consent_uniqueness_and_cancellation(env):
    client, _, h, users, base, people = prepare(env)
    own_id = users["athlete"]["athlete_id"]
    team = ok(
        client.post(
            base + "/teams",
            headers=h["athlete"],
            json={"name": "Первая", "captain_id": own_id},
        ),
        201,
    )
    assert team["members"][0]["status"] == "accepted"
    url = base + f"/teams/{team['id']}"
    assert (
        client.post(
            base + "/teams",
            headers=h["athlete"],
            json={"name": "Вторая", "captain_id": people[0][1]},
        ).status_code
        == 403
    )
    other = ok(
        client.post(
            base + "/teams",
            headers=people[1][0],
            json={"name": "Вторая", "captain_id": people[1][1]},
        ),
        201,
    )
    other_url = base + f"/teams/{other['id']}"
    for target, headers in [(url, h["athlete"]), (other_url, people[1][0])]:
        ok(
            client.post(
                target + "/members", headers=headers, json={"athlete_id": people[0][1]}
            ),
            201,
        )
    ok(
        client.patch(
            url + "/response", headers=people[0][0], json={"status": "accepted"}
        )
    )
    assert (
        client.patch(
            other_url + "/response", headers=people[0][0], json={"status": "accepted"}
        ).status_code
        == 409
    )
    assert client.post(url + "/submit", headers=people[1][0]).status_code == 403
    ok(
        client.post(
            url + "/cancel",
            headers=h["athlete"],
            json={"reason": "Команда снялась до подачи"},
        )
    )
    ok(
        client.patch(
            other_url + "/response", headers=people[0][0], json={"status": "accepted"}
        )
    )
    ok(client.post(other_url + "/submit", headers=people[1][0]))
    # Withdrawing consent returns the entire pending application to editing.
    response = ok(
        client.patch(
            other_url + "/response", headers=people[0][0], json={"status": "declined"}
        )
    )
    assert response["status"] == "returned"
    assert (
        client.patch(
            other_url + "/review", headers=h["admin"], json={"status": "approved"}
        ).status_code
        == 409
    )


def test_team_return_replacement_and_readmission(env):
    client, _, h, _, base, people = prepare(env)
    team, url = create_coach_team(client, h, base, people)
    for headers, _ in people[:2]:
        ok(
            client.patch(
                url + "/response", headers=headers, json={"status": "accepted"}
            )
        )
    ok(client.post(url + "/submit", headers=h["coach"]))
    assert (
        client.patch(
            url + "/review", headers=h["admin"], json={"status": "returned"}
        ).status_code
        == 422
    )
    ok(
        client.patch(
            url + "/review",
            headers=h["admin"],
            json={"status": "returned", "comment": "Уточните название команды"},
        )
    )
    ok(
        client.put(
            url,
            headers=h["coach"],
            json={"name": "ОренКод 2", "captain_id": people[0][1]},
        )
    )
    ok(client.post(url + "/submit", headers=h["coach"]))
    ok(client.patch(url + "/review", headers=h["admin"], json={"status": "approved"}))
    ok(
        client.post(
            url + "/reopen",
            headers=h["coach"],
            json={"reason": "Замена заболевшего участника"},
        )
    )
    assert not any(
        a["status"] == "approved"
        for a in ok(client.get(base, headers=h["admin"]))["applications"]
    )
    ok(client.delete(url + f"/members/{people[1][1]}", headers=h["coach"]), 204)
    ok(
        client.post(
            url + "/members", headers=h["coach"], json={"athlete_id": people[2][1]}
        ),
        201,
    )
    assert client.post(url + "/submit", headers=h["coach"]).status_code == 422
    ok(
        client.patch(
            url + "/response", headers=people[2][0], json={"status": "accepted"}
        )
    )
    ok(client.post(url + "/submit", headers=h["coach"]))
    ok(client.patch(url + "/review", headers=h["admin"], json={"status": "approved"}))
    admitted = {
        a["athlete_id"]
        for a in ok(client.get(base, headers=h["admin"]))["applications"]
        if a["status"] == "approved"
    }
    assert admitted == {people[0][1], people[2][1]}


@pytest.mark.parametrize("problem", ["age", "discipline", "suspension"])
def test_team_eligibility_rechecked_on_submission_and_review(env, problem):
    client, factory, h, _, base, people = prepare(env)
    _, url = create_coach_team(client, h, base, people)
    for headers, _ in people[:2]:
        ok(
            client.patch(
                url + "/response", headers=headers, json={"status": "accepted"}
            )
        )
    with factory() as db:
        athlete = db.get(Athlete, people[1][1])
        if problem == "age":
            original = athlete.user.birth_date
            athlete.user.birth_date = date(1900, 1, 1)
        elif problem == "discipline":
            enrollment = db.get(AthleteDiscipline, (athlete.id, 1))
            original = enrollment.start_year
            enrollment.start_year = date.today().year + 1
        else:
            athlete.suspended_until = date.today() + timedelta(days=5)
        db.commit()
    assert client.post(url + "/submit", headers=h["coach"]).status_code == 422
    with factory() as db:
        athlete = db.get(Athlete, people[1][1])
        if problem == "age":
            athlete.user.birth_date = original
        elif problem == "discipline":
            db.get(AthleteDiscipline, (athlete.id, 1)).start_year = original
        else:
            athlete.suspended_until = None
        db.commit()
    ok(client.post(url + "/submit", headers=h["coach"]))
    with factory() as db:
        db.get(Athlete, people[1][1]).suspended_until = date.today() + timedelta(days=5)
        db.commit()
    assert (
        client.patch(
            url + "/review", headers=h["admin"], json={"status": "approved"}
        ).status_code
        == 422
    )


def test_team_limits_coach_scope_captain_decline_and_deadline(env):
    client, factory, h, users, base, people = prepare(env)
    team, url = create_coach_team(client, h, base, people)
    assert (
        client.post(
            url + "/members",
            headers=h["coach"],
            json={"athlete_id": users["athlete"]["athlete_id"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            url + "/members", headers=h["judge"], json={"athlete_id": people[2][1]}
        ).status_code
        == 403
    )
    ok(
        client.patch(
            url + "/response", headers=people[0][0], json={"status": "declined"}
        )
    )
    ok(
        client.put(
            url,
            headers=h["coach"],
            json={"name": "Новый капитан", "captain_id": people[1][1]},
        )
    )
    ok(client.delete(url + f"/members/{people[0][1]}", headers=h["coach"]), 204)
    assert client.post(url + "/submit", headers=h["coach"]).status_code == 422
    ok(
        client.post(
            url + "/members", headers=h["coach"], json={"athlete_id": people[0][1]}
        ),
        201,
    )
    ok(
        client.post(
            url + "/members", headers=h["coach"], json={"athlete_id": people[2][1]}
        ),
        201,
    )
    fourth, aid4 = login(client, "athlete4")
    assert (
        client.post(
            url + "/members", headers=h["coach"], json={"athlete_id": aid4}
        ).status_code
        == 422
    )
    # Database also enforces one accepted team per athlete, independently of API.
    with factory() as db:
        assert db.scalar(select(CompetitionTeamMember.id))
        db.get(Competition, team["competition_id"]).deadline = date.today() - timedelta(
            days=1
        )
        db.commit()
    assert client.post(url + "/submit", headers=h["coach"]).status_code == 409
    assert (
        client.patch(
            url + "/response", headers=people[1][0], json={"status": "accepted"}
        ).status_code
        == 409
    )


def test_team_candidate_search_and_unicode_names(env):
    client, factory, h, users, base, people = prepare(env)
    team, url = create_coach_team(client, h, base, people)
    assert (
        client.post(
            base + "/teams",
            headers=people[2][0],
            json={"name": "ОРЕНКОД", "captain_id": people[2][1]},
        ).status_code
        == 409
    )
    assert client.get(base + "/team-candidates", headers=h["coach"]).status_code == 422
    assert (
        client.get(base + "/team-candidates?q=x", headers=h["coach"]).status_code == 422
    )
    full_name = team["captain"]
    found = ok(
        client.get(
            base + "/team-candidates",
            params={"q": full_name.upper()},
            headers=h["coach"],
        )
    )
    assert people[0][1] in {a["id"] for a in found}
    assert all(
        set(a) == {"id", "public_id", "full_name", "organization", "municipality"}
        for a in found
    )
    with factory() as db:
        outsider_name = db.get(Athlete, users["athlete"]["athlete_id"]).user.full_name
    assert (
        ok(
            client.get(
                base + "/team-candidates",
                params={"q": outsider_name},
                headers=h["coach"],
            )
        )
        == []
    )
    assert (
        client.get(base + "/team-candidates?q=Демо", headers=h["judge"]).status_code
        == 403
    )


def test_two_admitted_teams_use_team_places(env):
    client, factory, h, users, base, people = prepare(env)
    all_people = [(h["athlete"], users["athlete"]["athlete_id"]), *people]
    team_ids = []
    for i in range(2):
        captain, member = all_people[i * 2 : i * 2 + 2]
        team = ok(
            client.post(
                base + "/teams",
                headers=captain[0],
                json={"name": f"Команда {i}", "captain_id": captain[1]},
            ),
            201,
        )
        url = base + f"/teams/{team['id']}"
        ok(
            client.post(
                url + "/members", headers=captain[0], json={"athlete_id": member[1]}
            ),
            201,
        )
        ok(
            client.patch(
                url + "/response", headers=member[0], json={"status": "accepted"}
            )
        )
        ok(client.post(url + "/submit", headers=captain[0]))
        ok(
            client.patch(
                url + "/review", headers=h["admin"], json={"status": "approved"}
            )
        )
        team_ids.append(team["id"])
    ok(client.patch(base + "/state", headers=h["admin"], json={"state": "closed"}))
    rows = [
        {"team_id": team_ids[0], "place": 1, "score": 100},
        {"team_id": team_ids[1], "place": 2, "score": 80},
    ]
    assert (
        client.post(
            base + "/results", headers=h["admin"], json={"team_results": rows[:1]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            base + "/results",
            headers=h["admin"],
            json={"team_results": [rows[0], rows[0]]},
        ).status_code
        == 422
    )
    ok(client.post(base + "/results", headers=h["admin"], json={"team_results": rows}))
    results = ok(client.get(base, headers=h["admin"]))["results"]
    assert sorted(r["place"] for r in results) == [1, 1, 2, 2]
