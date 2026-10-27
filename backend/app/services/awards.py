"""Governor prizes: candidates are found automatically from published protocols
of the year by the amount reference; the federation moves them through the
petition statuses."""

from datetime import date
from sqlalchemy import select
from app.models import *

# Default amounts in rubles; the federation edits them in the reference.
DEFAULT_AMOUNTS = [
    ("russian_championship", (100000, 75000, 50000)),
    ("russian_junior", (60000, 45000, 30000)),
    ("interregional", (30000, 20000, 15000)),
    ("regional", (0, 0, 0)),
]
STATUSES = ["candidate", "nominated", "awarded", "rejected"]


def deadline(year):
    """Petitions for the achievements of a year are submitted by February 1."""
    return date(year + 1, 2, 1)


def current_year(today=None):
    today = today or date.today()
    return today.year - 1 if today.month == 1 else today.year


def amounts(db):
    return {
        r.level: (r.first, r.second, r.third)
        for r in db.scalars(select(GovernorAwardRule))
    }


def achievements(db, year):
    """athlete_id -> achievements of the year that carry a prize, best first."""
    prices = amounts(db)
    found = {}
    for result, comp in db.execute(
        select(CompetitionResult, Competition)
        .join(Competition, Competition.id == CompetitionResult.competition_id)
        .where(
            Competition.state == "published",
            Competition.start_date >= date(year, 1, 1),
            Competition.start_date <= date(year, 12, 31),
            CompetitionResult.place <= 3,
        )
    ):
        amount = prices.get(comp.rating_level, (0, 0, 0))[result.place - 1]
        if not amount:
            continue
        found.setdefault(result.athlete_id, []).append(
            {
                "competition_id": comp.id,
                "title": comp.title,
                "date": comp.start_date.isoformat(),
                "level": comp.rating_level,
                "place": result.place,
                "team_name": result.team_name,
                "amount": amount,
            }
        )
    for items in found.values():
        items.sort(key=lambda a: (-a["amount"], a["place"], a["date"]))
    return found


def suspended(athlete, year):
    """Suspension active at the end of the year (or today for the current one)."""
    at = min(date(year, 12, 31), date.today())
    return bool(athlete.suspended_until and athlete.suspended_until >= at)


def award_list(db, year):
    found = achievements(db, year)
    decisions = {
        a.athlete_id: a
        for a in db.scalars(select(GovernorAward).where(GovernorAward.year == year))
    }
    organizations = {o.id: o.name for o in db.scalars(select(Organization))}
    items = []
    for athlete_id in found.keys() | decisions.keys():
        athlete = db.get(Athlete, athlete_id)
        own = found.get(athlete_id, [])
        decision = decisions.get(athlete_id)
        blocked = suspended(athlete, year)
        items.append(
            {
                "athlete_id": athlete_id,
                "full_name": athlete.user.full_name,
                "organization": organizations.get(athlete.organization_id),
                "municipality": athlete.municipality,
                "achievements": own,
                # the prize is paid once a year, by the best achievement
                "basis": decision.basis if decision else (own[0] if own else None),
                "amount": decision.amount if decision else (own[0]["amount"] if own else 0),
                "status": decision.status if decision else "candidate",
                "eligible": bool(own) and not blocked,
                "suspended": blocked,
                "comment": decision.comment if decision else "",
                "order_number": decision.order_number if decision else None,
                "updated_at": decision.updated_at if decision else None,
            }
        )
    items.sort(
        key=lambda i: (
            STATUSES.index(i["status"]) if i["status"] != "rejected" else 9,
            -i["amount"],
            i["full_name"],
        )
    )
    totals = {s: sum(i["status"] == s for i in items) for s in STATUSES}
    totals["nominated_amount"] = sum(
        i["amount"] for i in items if i["status"] in ("nominated", "awarded")
    )
    totals["awarded_amount"] = sum(
        i["amount"] for i in items if i["status"] == "awarded"
    )
    return {
        "year": year,
        "deadline": deadline(year),
        "items": items,
        "totals": totals,
    }
