from sqlalchemy import select
from app.models import AthleteCoach, Athlete, Competition, CompetitionResult


def test_coaching_summary_filters_and_access(env):
    client, factory, headers, users = env
    links = client.get("/api/links", headers=headers["coach"]).json()
    link = next(l for l in links if l["status"] == "active")
    athlete_id = link["athlete_id"]
    url = f"/api/coaching/athletes/{athlete_id}/summary"
    with factory() as db:
        expected = db.execute(
            select(CompetitionResult, Competition)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id == athlete_id,
                Competition.state == "published",
            )
        ).all()
        outsider = next(
            a.id
            for a in db.scalars(select(Athlete))
            if a.id not in {l["athlete_id"] for l in links if l["status"] == "active"}
        )
    response = client.get(url, headers=headers["coach"])
    assert response.status_code == 200, response.text
    data = response.json()
    assert {r["id"] for r in data["results"]} == {r.id for r, _ in expected}
    assert data["stats"] == {
        "performances": len(expected),
        "wins": sum(r.place == 1 for r, _ in expected),
        "podiums": sum(r.place <= 3 for r, _ in expected),
        "best_place": min((r.place for r, _ in expected), default=None),
    }
    assert expected  # seeded ward has published results
    year = expected[0][1].start_date.year
    discipline = expected[0][1].discipline_id
    filtered = client.get(
        url,
        params={"year": year, "discipline_id": discipline},
        headers=headers["coach"],
    ).json()
    assert {r["id"] for r in filtered["results"]} == {
        r.id
        for r, c in expected
        if c.start_date.year == year and c.discipline_id == discipline
    }
    assert filtered["stats"]["performances"] == len(filtered["results"])
    empty_year = next(y for y in range(1970, 2101) if y not in data["years"])
    empty = client.get(
        url, params={"year": empty_year}, headers=headers["coach"]
    ).json()
    assert empty["results"] == []
    assert empty["stats"] == {
        "performances": 0,
        "wins": 0,
        "podiums": 0,
        "best_place": None,
    }
    assert (
        client.get(url, params={"year": 0}, headers=headers["coach"]).status_code == 422
    )
    assert (
        client.get(
            f"/api/coaching/athletes/{outsider}/summary", headers=headers["coach"]
        ).status_code
        == 403
    )
    assert client.get(url, headers=headers["athlete"]).status_code == 403
    assert client.get(url, headers=headers["judge"]).status_code == 403
    assert client.get(url).status_code in (401, 403)
    assert client.get(url, headers=headers["admin"]).status_code == 200
    with factory() as db:
        for relation in db.scalars(
            select(AthleteCoach).where(AthleteCoach.athlete_id == athlete_id)
        ):
            relation.status = "paused"
        db.commit()
    assert client.get(url, headers=headers["coach"]).status_code == 403


def test_coaching_summary_excludes_unpublished_results(env):
    client, factory, headers, _ = env
    link = next(
        l
        for l in client.get("/api/links", headers=headers["coach"]).json()
        if l["status"] == "active"
    )
    url = f"/api/coaching/athletes/{link['athlete_id']}/summary"
    before = client.get(url, headers=headers["coach"]).json()
    result = before["results"][0]
    with factory() as db:
        db.get(Competition, result["competition_id"]).state = "closed"
        db.commit()
    after = client.get(url, headers=headers["coach"]).json()
    assert result["id"] not in {r["id"] for r in after["results"]}
    assert after["stats"]["performances"] == before["stats"]["performances"] - 1
