from datetime import date, timedelta
from sqlalchemy import select
from app.models import Athlete, AthleteCoach, EvskRule, RankApplication, SportsRank


def path_for(path, discipline_id=1):
    return next(d for d in path["disciplines"] if d["id"] == discipline_id)


def test_path_shows_rank_goals_and_next_step(env):
    client, factory, headers, users = env
    athlete_id = users["athlete"]["athlete_id"]
    res = client.get(f"/api/athletes/{athlete_id}/path", headers=headers["athlete"])
    assert res.status_code == 200, res.text
    data = res.json()
    algo = path_for(data)
    # Seeded: III expiring in three weeks, first places at both demo events.
    assert algo["current_rank"] == "III"
    assert algo["next_rank"] == "II"
    assert [g["rank"] for g in algo["goals"]] == ["II", "I", "КМС"]
    goals = {g["rank"]: g for g in algo["goals"]}
    assert len(goals["II"]["achieved"]) == 1
    assert len(goals["I"]["achieved"]) == 1
    assert goals["КМС"]["achieved"] == []
    assert algo["next_step"]["kind"] == "confirm"
    assert algo["stats"]["performances"] == 2
    assert algo["timeline"][0]["kind"] == "start"
    assert {e["kind"] for e in algo["timeline"]} == {"start", "result", "rank"}
    assert data["summary"]["to_confirm"] == 1
    assert data["summary"]["ready_to_apply"] == 2
    # Only unmet goals mark upcoming starts; the seeded ones are regional.
    assert not any(c["counts_for_goal"] for c in algo["upcoming"])

    # A fresh rank: the highest matched goal becomes the next step.
    with factory() as db:
        rank = db.scalar(select(SportsRank).where(SportsRank.athlete_id == athlete_id))
        rank.expires_on = date.today() + timedelta(days=400)
        db.commit()

    def step():
        url = f"/api/athletes/{athlete_id}/path"
        return path_for(client.get(url, headers=headers["athlete"]).json())

    def apply(goal):
        with factory() as db:
            db.add(
                RankApplication(
                    athlete_id=athlete_id,
                    result_id=goal["achieved"][0]["result_id"],
                    submitted_by=users["athlete"]["id"],
                    name=goal["rank"],
                )
            )
            db.commit()

    algo = step()
    assert algo["next_step"]["kind"] == "apply"
    assert algo["next_step"]["rank"] == "I"
    apply(goals["II"])
    algo = step()
    assert {g["rank"]: g for g in algo["goals"]}["II"]["achieved"][0][
        "application"
    ] == "pending"
    assert algo["next_step"]["rank"] == "I"
    apply(goals["I"])
    algo = step()
    assert algo["next_step"]["kind"] == "wait"
    assert "«I»" in algo["next_step"]["text"]


def test_path_without_rules_and_access(env):
    client, factory, headers, users = env
    with factory() as db:
        for rule in db.scalars(select(EvskRule)):
            db.delete(rule)
        ward = db.scalar(
            select(AthleteCoach.athlete_id).where(AthleteCoach.status == "active")
        )
        outsider = next(
            a.id
            for a in db.scalars(select(Athlete))
            if a.id != ward
            and not db.scalar(
                select(AthleteCoach).where(
                    AthleteCoach.athlete_id == a.id, AthleteCoach.status == "active"
                )
            )
        )
        db.commit()
    url = f"/api/athletes/{ward}/path"
    data = client.get(url, headers=headers["coach"])
    assert data.status_code == 200, data.text
    for item in data.json()["disciplines"]:
        assert item["goals"] == []
        assert item["next_step"]["kind"] in ("none", "confirm")
    assert client.get(url, headers=headers["admin"]).status_code == 200
    assert client.get(url, headers=headers["judge"]).status_code == 403
    assert client.get(url).status_code in (401, 403)
    assert (
        client.get(f"/api/athletes/{outsider}/path", headers=headers["coach"]).status_code
        == 403
    )
    own = users["athlete"]["athlete_id"]
    if own != ward:
        assert client.get(url, headers=headers["athlete"]).status_code == 403


def test_glossary_is_public(env):
    client, factory, headers, users = env
    res = client.get("/api/public/glossary")
    assert res.status_code == 200, res.text
    data = res.json()
    ids = {t["id"] for t in data["terms"]}
    assert {"evsk", "rank", "rating"} <= ids
    # Related links point to existing terms only.
    assert all(r in ids for t in data["terms"] for r in t["related"])
    assert all(t["category"] in data["categories"] for t in data["terms"])
    assert data["ladder"][0] == "Без разряда"
    regional = next(l for l in data["levels"] if l["id"] == "regional")
    assert regional["points"] == [40, 30, 20]
    assert [r["rank"] for r in data["evsk"]] == ["II", "I", "КМС"]
    assert "Демо" in data["evsk"][0]["source"]
