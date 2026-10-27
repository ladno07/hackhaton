from datetime import date, timedelta
from sqlalchemy import select
from app.models import Athlete, AuditLog, Notification
from app.services.awards import current_year, deadline
from tests.test_ministry import ministry_login

# demo competitions: regional (60 days ago) and interregional cup (30 days ago)
YEAR = (date.today() - timedelta(days=30)).year


def awards(client, h, year=YEAR):
    res = client.get(f"/api/governor-awards?year={year}", headers=h)
    assert res.status_code == 200, res.text
    return res.json()


def test_candidates_from_protocols(env):
    client, factory, headers, users = env
    data = awards(client, headers["admin"])
    assert data["deadline"] == f"{YEAR + 1}-02-01"
    items = data["items"]
    # only interregional places 1–3 carry a prize; regional amounts are zero
    assert len(items) == 3
    assert all(i["basis"]["level"] == "interregional" for i in items)
    assert sorted(i["amount"] for i in items) == [15000, 20000, 30000]
    # demo: the cup winner is already in the petition
    assert [i["status"] for i in items].count("nominated") == 1
    assert data["totals"]["candidate"] == 2
    assert data["totals"]["nominated_amount"] == 30000

    # the reference changes the list: regional winners become candidates
    res = client.put(
        "/api/governor-award-rules/regional",
        json={"first": 10000, "second": 0, "third": 0},
        headers=headers["admin"],
    )
    assert res.status_code == 200, res.text
    items = awards(client, headers["admin"])["items"]
    assert len(items) == 3  # regional winner also won the cup
    winner = next(i for i in items if i["status"] == "nominated")
    assert [a["level"] for a in winner["achievements"]] == ["interregional", "regional"]

    # a suspended athlete stays in the list but cannot be put forward
    third = next(i for i in items if i["amount"] == 15000)
    with factory() as db:
        db.get(Athlete, third["athlete_id"]).suspended_until = date.today() + timedelta(days=90)
        db.commit()
    item = next(
        i for i in awards(client, headers["admin"])["items"] if i["athlete_id"] == third["athlete_id"]
    )
    assert item["suspended"] and not item["eligible"]
    res = client.put(
        f"/api/governor-awards/{YEAR}/{third['athlete_id']}",
        json={"status": "nominated"},
        headers=headers["admin"],
    )
    assert res.status_code == 409


def test_status_flow(env):
    client, factory, headers, users = env
    items = awards(client, headers["admin"])["items"]
    second = next(i for i in items if i["amount"] == 20000)
    url = f"/api/governor-awards/{YEAR}/{second['athlete_id']}"

    def put(body, h=headers["admin"]):
        return client.put(url, json=body, headers=h)

    assert put({"status": "awarded", "order_number": "1-п"}).status_code == 409
    assert put({"status": "rejected"}).status_code == 422  # reason is required
    res = put({"status": "nominated", "comment": "Решение совета федерации"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "nominated" and res.json()["amount"] == 20000

    # amount is fixed in the petition even if the reference changes later
    client.put(
        "/api/governor-award-rules/interregional",
        json={"first": 1, "second": 1, "third": 1},
        headers=headers["admin"],
    )
    assert next(
        i for i in awards(client, headers["admin"])["items"] if i["athlete_id"] == second["athlete_id"]
    )["amount"] == 20000

    assert put({"status": "awarded"}).status_code == 422  # order number required
    res = put({"status": "awarded", "order_number": "12-рп"})
    assert res.status_code == 200, res.text
    assert res.json()["order_number"] == "12-рп"
    assert put({"status": "candidate"}).status_code == 409
    with factory() as db:
        athlete = db.get(Athlete, second["athlete_id"])
        notice = db.scalar(
            select(Notification).where(
                Notification.user_id == athlete.user_id,
                Notification.title == "Премия Губернатора",
            )
        )
        assert notice and "12-рп" in notice.body
        actions = set(
            db.scalars(select(AuditLog.action).where(AuditLog.entity.like("governor_award%")))
        )
    assert {
        "Изменение статуса премии Губернатора",
        "Изменение сумм премий Губернатора",
    } <= actions

    # ministry reads and exports, but cannot change statuses or amounts
    h = ministry_login(client)
    assert awards(client, h)["totals"]["awarded"] == 1
    assert put({"status": "nominated", "comment": "x"}, h).status_code == 403
    assert (
        client.put(
            "/api/governor-award-rules/regional",
            json={"first": 1, "second": 1, "third": 1},
            headers=h,
        ).status_code
        == 403
    )
    for fmt in ("pdf", "docx", "xlsx"):
        res = client.get(f"/api/exports/governor-awards.{fmt}?year={YEAR}", headers=h)
        assert res.status_code == 200, (fmt, res.text)
        assert len(res.content) > 1000
    # other roles do not see the list
    assert client.get("/api/governor-awards", headers=headers["coach"]).status_code == 403

    # cancelling an award needs a reason; withdrawn candidates return to the list
    assert put({"status": "nominated"}).status_code == 422
    assert put({"status": "nominated", "comment": "Ошибка в распоряжении"}).status_code == 200
    res = put({"status": "candidate"})
    assert res.status_code == 200 and res.json()["status"] == "candidate"


def test_unknown_athlete_and_year(env):
    client, factory, headers, users = env
    res = client.put(
        f"/api/governor-awards/{YEAR}/999999",
        json={"status": "nominated"},
        headers=headers["admin"],
    )
    assert res.status_code == 404
    future = date.today().year + 1
    assert client.get(f"/api/governor-awards?year={future}", headers=headers["admin"]).status_code == 422
    assert awards(client, headers["admin"], YEAR - 5)["items"] == []
    default = client.get("/api/governor-awards", headers=headers["admin"]).json()
    assert default["year"] == current_year()


def test_deadline_rules():
    assert deadline(2026) == date(2027, 2, 1)
    assert current_year(date(2027, 1, 20)) == 2026
    assert current_year(date(2026, 10, 27)) == 2026
