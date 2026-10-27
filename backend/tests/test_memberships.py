from datetime import date, timedelta
from sqlalchemy import select
from app.models import *


def org_rows(client, h, org_id, year):
    report = client.get(
        f"/api/reports/population?start_year={year - 1}&end_year={year}"
        f"&organization_id={org_id}",
        headers=h,
    )
    assert report.status_code == 200, report.text
    return report.json()


def profile_body(profile, **changes):
    body = {
        k: profile[k]
        for k in ["full_name", "organization_id", "municipality", "training_stage"]
    }
    body["disciplines"] = [
        {k: d[k] for k in ["discipline_id", "start_year", "end_year"]}
        for d in profile["disciplines"]
    ]
    return {**body, **changes}


def test_demo_transfer_in_history(env):
    client, factory, h, _ = env
    year = date.today().year
    with factory() as db:
        moved = db.scalar(
            select(Athlete).join(User).where(User.email == "athlete1@demo.example")
        )
    history = client.get(f"/api/athletes/{moved.id}", headers=h["admin"]).json()[
        "organization_history"
    ]
    assert [(p["organization"], p["end_date"]) for p in history] == [
        ("Демо · Код Оренбурга", date(year - 1, 8, 31).isoformat()),
        ("Демо · Орский алгоритм", None),
    ]


def test_transfer_moves_athlete_between_organizations(env):
    client, _, h, u = env
    year = date.today().year
    aid = u["athlete"]["athlete_id"]
    profile = client.get(f"/api/athletes/{aid}", headers=h["admin"]).json()
    old_org = profile["organization_id"]
    new_org = next(
        o["id"]
        for o in client.get("/api/metadata", headers=h["admin"]).json()[
            "organizations"
        ]
        if o["id"] != old_org
    )
    old_before = org_rows(client, h["admin"], old_org, year)["totals"]
    new_before = org_rows(client, h["admin"], new_org, year)["totals"]
    since = date(year, 1, 1)
    if since <= date.fromisoformat(profile["organization_history"][-1]["start_date"]):
        since = date.today()
    future = client.put(
        f"/api/athletes/{aid}",
        headers=h["admin"],
        json=profile_body(
            profile,
            organization_id=new_org,
            organization_since=(date.today() + timedelta(days=1)).isoformat(),
        ),
    )
    assert future.status_code == 422
    res = client.put(
        f"/api/athletes/{aid}",
        headers=h["admin"],
        json=profile_body(
            profile, organization_id=new_org, organization_since=since.isoformat()
        ),
    )
    assert res.status_code == 200, res.text
    history = res.json()["organization_history"]
    assert [p["organization_id"] for p in history][-2:] == [old_org, new_org]
    assert history[-2]["end_date"] == (since - timedelta(days=1)).isoformat()
    assert history[-1]["end_date"] is None
    old_after = org_rows(client, h["admin"], old_org, year)["totals"]
    new_after = org_rows(client, h["admin"], new_org, year)["totals"]
    # Previous year stays with the old organization, the current one moves.
    assert old_after[0] == old_before[0] and new_after[0] == new_before[0]
    assert old_after[1]["count"] == old_before[1]["count"] - 1
    assert new_after[1]["count"] == new_before[1]["count"] + 1
    # A transfer cannot reach into the closed history.
    back = client.put(
        f"/api/athletes/{aid}",
        headers=h["admin"],
        json=profile_body(
            res.json(),
            organization_id=old_org,
            organization_since=(since - timedelta(days=1)).isoformat(),
        ),
    )
    assert back.status_code == 422
    # Leaving the organization closes the period without opening a new one.
    gone = client.put(
        f"/api/athletes/{aid}",
        headers=h["athlete"],
        json=profile_body(res.json(), organization_id=None),
    )
    assert gone.status_code == 200, gone.text
    assert gone.json()["organization"] == "Без организации"
    assert all(p["end_date"] for p in gone.json()["organization_history"])
