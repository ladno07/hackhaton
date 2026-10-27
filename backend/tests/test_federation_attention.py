from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from app.models import (
    Athlete,
    Competition,
    CompetitionApplication,
    CompetitionResult,
    Deadline,
    Judge,
    JudgeCategory,
    RankApplication,
    SportsRank,
)


def test_federation_attention_lists_every_kind(env):
    client, factory, headers, users = env
    today = date.today()
    with factory() as db:
        result = db.scalars(select(CompetitionResult)).first()
        competition = db.get(Competition, result.competition_id)
        applied = select(CompetitionApplication.athlete_id).where(
            CompetitionApplication.competition_id == competition.id
        )
        athlete = db.scalars(select(Athlete).where(Athlete.id.not_in(applied))).first()
        judges = db.scalars(select(Judge)).all()
        active_judge = next(j for j in judges if j.user_id == users["judge"]["id"])

        def rank(name, days):
            r = SportsRank(
                athlete_id=result.athlete_id,
                discipline_id=competition.discipline_id,
                name=name,
                assigned_on=today - timedelta(days=700),
                expires_on=today + timedelta(days=days),
                order_number="Тест",
                result_id=result.id,
            )
            db.add(r)
            return r

        soon, later, expired = (
            rank("Тест скоро", 10),
            rank("Тест позже", 60),
            rank("Тест истёк", -1),
        )
        category = JudgeCategory(
            judge_id=active_judge.id,
            name="Тест категория",
            assigned_on=today - timedelta(days=700),
            expires_on=today + timedelta(days=5),
            order_number="Тест",
        )
        db.add(category)
        archived = next(j for j in judges if j.id != active_judge.id)
        archived.archived_at = datetime.now(timezone.utc)
        hidden = JudgeCategory(
            judge_id=archived.id,
            name="Тест архив",
            assigned_on=today - timedelta(days=700),
            expires_on=today + timedelta(days=5),
            order_number="Тест",
        )
        db.add(hidden)
        request = RankApplication(
            judge_id=active_judge.id,
            submitted_by=users["judge"]["id"],
            name="Тест заявка",
            kind="assignment",
        )
        db.add(request)
        application = CompetitionApplication(
            competition_id=competition.id,
            athlete_id=athlete.id,
            submitted_by=users["admin"]["id"],
        )
        db.add(application)
        overdue = Deadline(title="Тест отчёт", due_on=today - timedelta(days=2))
        done = Deadline(title="Тест сдан", due_on=today + timedelta(days=3), done=True)
        db.add_all([overdue, done])
        db.commit()
        ids = {
            "soon": soon.id,
            "later": later.id,
            "expired": expired.id,
            "category": category.id,
            "hidden": hidden.id,
            "request": request.id,
            "overdue": overdue.id,
            "done": done.id,
        }
        pending = len(
            db.scalars(
                select(CompetitionApplication).where(
                    CompetitionApplication.competition_id == competition.id,
                    CompetitionApplication.status == "pending",
                )
            ).all()
        )

    url = "/api/dashboard/attention"
    response = client.get(url, headers=headers["admin"])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["window_days"] == 30
    items = data["items"]
    assert data["counts"] == {
        k: sum(i["kind"] == k for i in items) for k in data["counts"]
    }
    assert all(data["counts"].values())
    by_kind = lambda kind: {i["id"]: i for i in items if i["kind"] == kind}

    comp = by_kind("applications")[competition.id]
    assert comp["detail"] == f"На рассмотрении: {pending}"
    assert comp["link"] == f"/competitions/{competition.id}"
    assert ids["request"] in by_kind("rank_applications")
    assert by_kind("rank_applications")[ids["request"]]["link"] == "/ranks"
    ranks = by_kind("ranks")
    assert ids["soon"] in ranks
    assert ids["later"] not in ranks and ids["expired"] not in ranks
    categories = by_kind("categories")
    assert ids["category"] in categories and ids["hidden"] not in categories
    reports = by_kind("reports")
    assert reports[ids["overdue"]]["overdue"] is True
    assert ids["done"] not in reports
    assert [i["due_on"] for i in items] == sorted(i["due_on"] for i in items)

    for role in ("athlete", "coach", "judge"):
        assert client.get(url, headers=headers[role]).status_code == 403
    assert client.get(url).status_code in (401, 403)
