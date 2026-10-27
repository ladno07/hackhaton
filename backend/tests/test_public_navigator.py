import json
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import func, select
from app.models import (
    Athlete,
    AthleteDiscipline,
    Coach,
    CoachDiscipline,
    Competition,
    Discipline,
    Organization,
    User,
)


def test_navigator_is_public_and_hides_personal_data(env):
    client, factory, headers, users = env
    today = date.today()
    with factory() as db:
        template = db.scalars(select(Competition)).first()
        discipline = db.scalars(select(Discipline)).first()

        def event(title, state, days):
            c = Competition(
                title=title,
                discipline_id=discipline.id,
                type_id=template.type_id,
                start_date=today + timedelta(days=days),
                end_date=today + timedelta(days=days),
                deadline=today + timedelta(days=max(days - 1, 0)),
                location="Оренбург",
                format="onsite",
                status="regional",
                rating_level="regional",
                calendar_plan="Тест",
                calendar_number="Т-1",
                state=state,
            )
            db.add(c)
            return c

        draft = event("Тест черновик", "draft", 10)
        opened = event("Тест открытый", "open", 10)
        past = event("Тест прошедший", "published", -30)
        # an organization whose only coach is archived must not be listed
        hidden = Organization(name="Тест скрытая", kind="Клуб", municipality="Тестовск")
        db.add(hidden)
        db.flush()
        ghost_user = User(
            email="ghost@demo.example",
            full_name="Тест Архивный",
            birth_date=date(1990, 1, 1),
            password_hash="x",
        )
        db.add(ghost_user)
        db.flush()
        ghost = Coach(
            user_id=ghost_user.id,
            organization_id=hidden.id,
            phone="+79990000000",
            archived_at=datetime.now(timezone.utc),
        )
        db.add(ghost)
        db.flush()
        db.add(CoachDiscipline(coach_id=ghost.id, discipline_id=discipline.id))
        db.commit()
        ids = {"draft": draft.id, "open": opened.id, "past": past.id}
        emails = db.scalars(select(User.email)).all()
        names = db.scalars(select(User.full_name)).all()
        phones = [p for p in db.scalars(select(Coach.phone)) if p]

    url = "/api/public/navigator"
    response = client.get(url)
    assert response.status_code == 200, response.text
    data = response.json()
    assert client.get(url, headers=headers["athlete"]).status_code == 200

    assert len(data["disciplines"]) == 6
    assert all(d["about"] for d in data["disciplines"])
    competitions = {c["id"]: c for c in data["competitions"]}
    assert ids["open"] in competitions
    assert competitions[ids["open"]]["registration_open"] is True
    assert ids["draft"] not in competitions and ids["past"] not in competitions
    starts = [c["start_date"] for c in data["competitions"]]
    assert starts == sorted(starts)

    places = data["places"]
    assert places and "Тест скрытая" not in {p["name"] for p in places}
    assert "Тестовск" not in data["municipalities"]
    assert all(p["coaches"] + p["athletes"] > 0 for p in places)
    for d in data["disciplines"]:
        assert d["organizations"] == sum(d["id"] in p["discipline_ids"] for p in places)

    # people with several disciplines are counted once
    with factory() as db:
        for p in places:
            expected = db.scalars(
                select(func.count(func.distinct(Athlete.id)))
                .join(AthleteDiscipline, AthleteDiscipline.athlete_id == Athlete.id)
                .where(
                    Athlete.organization_id == p["id"],
                    AthleteDiscipline.end_year.is_(None),
                )
            ).one()
            assert p["athletes"] == expected

    raw = json.dumps(data, ensure_ascii=False)
    assert "@" not in raw
    assert not any(p in raw for p in phones)
    assert not any(n in raw for n in names)
