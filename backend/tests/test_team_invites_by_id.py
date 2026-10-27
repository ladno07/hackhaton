import re
from sqlalchemy import select
from app.models import Athlete, AthleteCoach, Coach
from test_competition_teams import prepare, ok


def public_id(client, headers):
    return ok(client.get("/api/auth/me", headers=headers))["athlete_public_id"]


def test_duplicate_names_invite_exact_recipient_by_public_id(env):
    client, factory, h, users, base, people = prepare(env)
    with factory() as db:
        for index, (_, aid) in enumerate(people[:2]):
            athlete = db.get(Athlete, aid)
            athlete.user.full_name = "Иван Иванов"
            athlete.municipality = ["Оренбург", "Орск"][index]
            athlete.organization_id = index + 1
        db.commit()
    ids = [public_id(client, headers) for headers, _ in people[:2]]
    assert ids[0] != ids[1]
    assert all(re.fullmatch(r"FSP-[0-9]{6,10}", value) for value in ids)
    found = ok(
        client.get(
            base + "/team-candidates", headers=h["athlete"], params={"q": "Иван Иванов"}
        )
    )
    assert {a["public_id"] for a in found} == set(ids)
    assert {a["municipality"] for a in found} == {"Оренбург", "Орск"}
    assert len({a["organization"] for a in found}) == 2
    assert all(
        set(a) == {"id", "public_id", "full_name", "organization", "municipality"}
        for a in found
    )
    selected = ok(
        client.get(
            base + "/team-candidates",
            headers=h["athlete"],
            params={"public_id": ids[1].lower()},
        )
    )
    assert len(selected) == 1 and selected[0]["id"] == people[1][1]
    team = ok(
        client.post(
            base + "/teams",
            headers=h["athlete"],
            json={
                "name": "Точный адресат",
                "captain_id": users["athlete"]["athlete_id"],
            },
        ),
        201,
    )
    url = base + f"/teams/{team['id']}"
    invited = ok(
        client.post(url + "/members", headers=h["athlete"], json={"public_id": ids[1]}),
        201,
    )
    assert {m["athlete_id"] for m in invited["members"]} == {
        users["athlete"]["athlete_id"],
        people[1][1],
    }
    assert (
        next(m for m in invited["members"] if m["athlete_id"] == people[1][1])[
            "public_id"
        ]
        == ids[1]
    )
    assert (
        client.patch(
            url + "/response", headers=people[0][0], json={"status": "accepted"}
        ).status_code
        == 403
    )
    ok(
        client.patch(
            url + "/response", headers=people[1][0], json={"status": "accepted"}
        )
    )
    event_prefix = f"competition-team:{team['competition_id']}:{team['id']}:"
    assert any(
        n["event_key"].startswith(event_prefix)
        for n in ok(client.get("/api/notifications", headers=people[1][0]))
    )
    assert not any(
        n["event_key"].startswith(event_prefix)
        for n in ok(client.get("/api/notifications", headers=people[0][0]))
    )
    with factory() as db:
        db.get(Athlete, people[1][1]).user.full_name = "Иван Петров"
        db.commit()
    assert public_id(client, people[1][0]) == ids[1]
    again = ok(
        client.get(
            base + "/team-candidates",
            headers=h["athlete"],
            params={"public_id": ids[1]},
        )
    )
    assert again[0]["full_name"] == "Иван Петров"
    profile = ok(client.get(f"/api/athletes/{people[1][1]}", headers=people[1][0]))
    assert profile["public_id"] == ids[1]


def test_coach_picker_lists_only_active_wards_of_competition_discipline(env):
    client, factory, h, users, base, people = prepare(env)
    with factory() as db:
        coach = db.scalar(select(Coach).where(Coach.user_id == users["coach"]["id"]))
        expected = set(
            db.scalars(
                select(AthleteCoach.athlete_id).where(
                    AthleteCoach.coach_id == coach.id,
                    AthleteCoach.discipline_id == 1,
                    AthleteCoach.status == "active",
                )
            )
        )
    choices = ok(client.get(base + "/team-candidates?mine=true", headers=h["coach"]))
    assert {a["id"] for a in choices} == expected
    assert all(a["public_id"] and a["organization"] for a in choices)
    outsider_id = public_id(client, h["athlete"])
    assert (
        ok(
            client.get(
                base + "/team-candidates",
                headers=h["coach"],
                params={"public_id": outsider_id},
            )
        )
        == []
    )
    assert (
        client.get(
            base + "/team-candidates?mine=true", headers=h["athlete"]
        ).status_code
        == 403
    )
    team = ok(
        client.post(
            base + "/teams",
            headers=h["coach"],
            json={"name": "Мои подопечные", "captain_id": people[0][1]},
        ),
        201,
    )
    url = base + f"/teams/{team['id']}"
    assert (
        client.post(
            url + "/members", headers=h["coach"], json={"public_id": outsider_id}
        ).status_code
        == 403
    )
    ok(
        client.post(
            url + "/members",
            headers=h["coach"],
            json={"public_id": public_id(client, people[1][0])},
        ),
        201,
    )
    with factory() as db:
        link = db.scalar(
            select(AthleteCoach).where(
                AthleteCoach.coach_id == coach.id,
                AthleteCoach.athlete_id == people[1][1],
                AthleteCoach.discipline_id == 1,
            )
        )
        link.status = "paused"
        db.commit()
    assert people[1][1] not in {
        a["id"]
        for a in ok(client.get(base + "/team-candidates?mine=true", headers=h["coach"]))
    }


def test_public_id_rejects_invalid_unknown_and_ambiguous_input(env):
    client, _, h, users, base, people = prepare(env)
    team = ok(
        client.post(
            base + "/teams",
            headers=h["athlete"],
            json={"name": "Проверка ID", "captain_id": users["athlete"]["athlete_id"]},
        ),
        201,
    )
    url = base + f"/teams/{team['id']}/members"
    for value in [
        "123",
        "FSP-000000",
        "FSP-0000001",
        "FSP-9999999999",
        "FSP-ABCDEF",
        "FSP-000001%",
    ]:
        assert (
            client.get(
                base + "/team-candidates",
                headers=h["athlete"],
                params={"public_id": value},
            ).status_code
            == 422
        )
        assert (
            client.post(
                url, headers=h["athlete"], json={"public_id": value}
            ).status_code
            == 422
        )
    assert (
        ok(
            client.get(
                base + "/team-candidates",
                headers=h["athlete"],
                params={"public_id": "FSP-999999"},
            )
        )
        == []
    )
    assert (
        client.post(
            url, headers=h["athlete"], json={"public_id": "FSP-999999"}
        ).status_code
        == 404
    )
    valid = public_id(client, people[0][0])
    assert (
        client.get(
            base + "/team-candidates",
            headers=h["athlete"],
            params={"public_id": valid, "q": "Иван"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            headers=h["athlete"],
            json={"public_id": valid, "athlete_id": people[0][1]},
        ).status_code
        == 422
    )
    assert client.post(url, headers=h["athlete"], json={}).status_code == 422
    assert (
        client.get(
            base + "/team-candidates", headers=h["judge"], params={"public_id": valid}
        ).status_code
        == 403
    )
    assert client.get(
        base + "/team-candidates", params={"public_id": valid}
    ).status_code in {401, 403}
