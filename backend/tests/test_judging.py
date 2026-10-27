from datetime import date, timedelta
from sqlalchemy import select
from app.models import Competition, CompetitionJudge, CompetitionResult, Judge, User


def assign_upcoming(factory):
    with factory() as db:
        judge = db.scalar(
            select(Judge).join(User).where(User.email == "judge@demo.example")
        )
        comp = db.scalar(
            select(Competition).where(Competition.end_date >= date.today())
        )
        if comp is None:
            comp = db.scalar(select(Competition))
            comp.start_date = comp.end_date = date.today() + timedelta(days=10)
        if not db.get(CompetitionJudge, (comp.id, judge.id)):
            db.add(
                CompetitionJudge(
                    competition_id=comp.id, judge_id=judge.id, position="Судья"
                )
            )
        db.commit()
        return judge.id, comp.id


def test_assignments_split_by_date(env):
    client, factory, headers, _ = env
    judge_id, upcoming_id = assign_upcoming(factory)
    upcoming = client.get(
        "/api/assignments", params={"scope": "upcoming"}, headers=headers["judge"]
    ).json()
    past = client.get(
        "/api/assignments", params={"scope": "past"}, headers=headers["judge"]
    ).json()
    everything = client.get("/api/assignments", headers=headers["judge"]).json()
    today = date.today().isoformat()
    assert upcoming_id in {a["competition_id"] for a in upcoming}
    assert past and all(a["end_date"] < today for a in past)
    assert all(a["end_date"] >= today for a in upcoming)
    assert len(upcoming) + len(past) == len(everything)
    assert all(a["judge_id"] == judge_id for a in everything)
    assert (
        client.get(
            "/api/assignments", params={"scope": "soon"}, headers=headers["judge"]
        ).status_code
        == 422
    )


def test_judging_report_and_export(env):
    client, factory, headers, _ = env
    _, upcoming_id = assign_upcoming(factory)
    response = client.get("/api/judging/report", headers=headers["judge"])
    assert response.status_code == 200, response.text
    data = response.json()
    ids = {i["competition_id"] for i in data["items"]}
    assert ids and upcoming_id not in ids
    with factory() as db:
        counts = {
            cid: len(
                db.scalars(
                    select(CompetitionResult).where(
                        CompetitionResult.competition_id == cid
                    )
                ).all()
            )
            for cid in ids
        }
    assert {i["competition_id"]: i["participants"] for i in data["items"]} == counts
    assert data["stats"]["competitions"] == len(ids)
    assert data["stats"]["participants"] == sum(counts.values())
    assert data["stats"]["chief"] == sum(
        i["position"] == "Главный судья" for i in data["items"]
    )
    empty_year = next(y for y in range(1970, 2101) if y not in data["years"])
    empty = client.get(
        "/api/judging/report", params={"year": empty_year}, headers=headers["judge"]
    ).json()
    assert empty["items"] == [] and empty["stats"]["competitions"] == 0
    for fmt in ("pdf", "docx", "xlsx"):
        export = client.get(f"/api/exports/judging.{fmt}", headers=headers["judge"])
        assert export.status_code == 200, export.text
        assert export.content
    assert (
        client.get("/api/exports/judging.txt", headers=headers["judge"]).status_code
        == 422
    )
    for role in ("athlete", "coach", "admin"):
        assert (
            client.get("/api/judging/report", headers=headers[role]).status_code == 403
        )
