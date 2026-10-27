from sqlalchemy import func, select
from app.models import Athlete, Competition, Notification, User
from app.routers.registry import MINISTRY_FIELDS
import app.seed as seed_module

READ_ONLY = "Кабинет Минспорта доступен только для просмотра"


def ministry_login(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "minsport@demo.example", "password": "DemoPass2026!"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["roles"] == ["ministry"]
    return {
        "Authorization": "Bearer " + res.json()["access_token"],
        "X-Active-Role": "ministry",
    }


def test_ministry_reads_statistics(env):
    client, factory, headers, users = env
    h = ministry_login(client)
    with factory() as db:
        athletes = db.scalar(select(func.count()).select_from(Athlete))
        competition = db.scalars(
            select(Competition).where(Competition.state == "published")
        ).first()
        drafts = {
            c.id for c in db.scalars(select(Competition).where(Competition.state == "draft"))
        }

    for url in [
        "/api/dashboard",
        "/api/metadata",
        "/api/results",
        "/api/ranks",
        "/api/ratings",
        "/api/team",
        "/api/rating-rules",
        "/api/judges",
        f"/api/competitions/{competition.id}",
        f"/api/exports/protocol/{competition.id}.pdf",
        "/api/reports/population",
        "/api/exports/population.xlsx",
        "/api/exports/team.pdf",
    ]:
        assert client.get(url, headers=h).status_code == 200, url

    assert client.get("/api/dashboard", headers=h).json()["athletes"] == athletes
    listed = {c["id"] for c in client.get("/api/competitions", headers=h).json()}
    assert listed and not listed & drafts

    registry = client.get("/api/athletes", headers=h).json()
    assert len(registry) == athletes
    assert set(registry[0]) == set(MINISTRY_FIELDS)
    coaches = client.get("/api/coaches", headers=h).json()
    private = {"phone", "contact_email", "email", "birth_date"}
    assert coaches and not private & set(coaches[0])
    card = client.get(f"/api/coaches/{coaches[0]['id']}", headers=h).json()
    assert not private & set(card)
    # the calendar only: no rank expiries of every athlete in the region
    assert {d["kind"] for d in client.get("/api/deadlines", headers=h).json()} <= {
        "competition"
    }


def test_ministry_cannot_change_or_see_internal_data(env):
    client, factory, headers, users = env
    h = ministry_login(client)
    with factory() as db:
        athlete = db.scalars(select(Athlete)).first()
        competition = db.scalars(select(Competition)).first()

    for url in [
        "/api/audit",
        "/api/users",
        "/api/dashboard/attention",
        f"/api/athletes/{athlete.id}",
        f"/api/exports/athlete/{athlete.id}.pdf",
        "/api/coaches?archived=true",
    ]:
        assert client.get(url, headers=h).status_code == 403, url

    writes = [
        ("post", "/api/competitions", {}),
        ("put", f"/api/competitions/{competition.id}", {}),
        ("patch", f"/api/competitions/{competition.id}/state", {"state": "open"}),
        ("patch", "/api/applications/1", {"status": "approved"}),
        ("put", "/api/team", {}),
        ("post", "/api/organizations", {"name": "x"}),
        ("post", "/api/links", {}),
        ("post", "/api/rank-applications", {}),
        ("put", f"/api/users/{users['admin']['id']}/roles", {"roles": ["ministry"]}),
        ("post", "/api/deadlines", {}),
        ("put", "/api/rating-rules/regional", {}),
    ]
    for method, url, body in writes:
        res = getattr(client, method)(url, json=body, headers=h)
        assert res.status_code == 403, (url, res.status_code)
        # rejected by the role guard itself, before validation or endpoint checks
        assert res.json()["detail"] == READ_ONLY, url

    with factory() as db:
        user_id = db.scalar(select(User.id).where(User.email == "minsport@demo.example"))
        db.add(
            Notification(
                user_id=user_id,
                title="Открыт приём заявок",
                body="Тест",
                event_key="competition-open:1:0",
            )
        )
        db.add(
            Notification(
                user_id=user_id,
                title="Заявка",
                body="Тест",
                event_key="application:1",
            )
        )
        db.commit()
    notices = client.get("/api/notifications", headers=h).json()
    items = notices if isinstance(notices, list) else notices["items"]
    keys = {n["title"] for n in items}
    assert "Открыт приём заявок" in keys and "Заявка" not in keys
    notice = next(n for n in items if n["title"] == "Открыт приём заявок")
    assert (
        client.patch(f"/api/notifications/{notice['id']}/read", headers=h).status_code
        == 200
    )


def test_ministry_role_is_assigned_only_by_federation(env):
    client, factory, headers, users = env
    res = client.post(
        "/api/auth/register",
        json={
            "email": "self-minister@demo.example",
            "password": "LongPassword2026!",
            "full_name": "Тест Самозванец",
            "birth_date": "1990-01-01",
            "role": "ministry",
            "consent": True,
        },
    )
    assert res.status_code == 422
    judge_id = users["judge"]["id"]
    res = client.put(
        f"/api/users/{judge_id}/roles",
        json={"roles": ["judge", "ministry"]},
        headers=headers["admin"],
    )
    assert res.status_code == 200, res.text
    # the demo admin can switch to the ministry cabinet
    switched = {**headers["admin"], "X-Active-Role": "ministry"}
    assert client.get("/api/reports/population", headers=switched).status_code == 200
    # loading demo data again does not duplicate the ministry account
    seed_module.seed(demo=True)
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.email == "minsport@demo.example")
            )
            == 1
        )
