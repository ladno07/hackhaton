from collections import defaultdict
from datetime import date
from sqlalchemy import select, delete, text
from app.models import *
from app.services.common import age_at

RANKS = [
    "Без разряда",
    "III юношеский",
    "II юношеский",
    "I юношеский",
    "III",
    "II",
    "I",
    "КМС",
    "МС",
    "МСМК",
]


def recalculate(db, season):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:season)"), {"season": season})
    # Immutable published protocols are the only source of rating points.
    rules = {r.level: r for r in db.scalars(select(RatingRule))}
    grouped = defaultdict(list)
    for result, comp in db.execute(
        select(CompetitionResult, Competition)
        .join(Competition, Competition.id == CompetitionResult.competition_id)
        .where(
            Competition.state == "published",
            Competition.start_date >= date(season, 1, 1),
            Competition.start_date <= date(season, 12, 31),
        )
    ):
        rule = rules.get(comp.level)
        points = (
            [rule.first, rule.second, rule.third][result.place - 1]
            if rule and result.place <= 3
            else 0
        )
        grouped[(result.athlete_id, comp.discipline_id)].append(
            {
                "competition_id": comp.id,
                "title": comp.title,
                "place": result.place,
                "points": points,
                "level": comp.level,
            }
        )
    db.execute(delete(Rating).where(Rating.season == season))
    for (athlete_id, discipline_id), breakdown in grouped.items():
        athlete = db.get(Athlete, athlete_id)
        if athlete.suspended_until and athlete.suspended_until >= date.today():
            continue
        coefficient = 1.2 if sum(b["place"] <= 3 for b in breakdown) >= 2 else 1.0
        db.add(
            Rating(
                athlete_id=athlete_id,
                discipline_id=discipline_id,
                season=season,
                points=round(sum(b["points"] for b in breakdown) * coefficient, 2),
                coefficient=coefficient,
                breakdown=breakdown,
            )
        )
    db.flush()


def ranking(db, season, discipline_id=None, min_age=0, max_age=100, min_rank=None):
    recalculate(db, season)
    query = (
        select(Rating)
        .where(Rating.season == season)
        .order_by(Rating.points.desc(), Rating.athlete_id)
    )
    if discipline_id:
        query = query.where(Rating.discipline_id == discipline_id)
    output = []
    for rating in db.scalars(query):
        athlete = db.get(Athlete, rating.athlete_id)
        age = age_at(athlete.user.birth_date)
        ranks = db.scalars(
            select(SportsRank).where(
                SportsRank.athlete_id == athlete.id,
                SportsRank.discipline_id == rating.discipline_id,
                SportsRank.expires_on >= date.today(),
            )
        ).all()
        rank = max(
            (r.name for r in ranks),
            key=lambda n: RANKS.index(n) if n in RANKS else 0,
            default="Без разряда",
        )
        if not min_age <= age <= max_age or (
            min_rank and RANKS.index(rank) < RANKS.index(min_rank)
        ):
            continue
        output.append(
            {
                "athlete_id": athlete.id,
                "full_name": athlete.user.full_name,
                "age": age,
                "rank": rank,
                "discipline_id": rating.discipline_id,
                "points": rating.points,
                "coefficient": rating.coefficient,
                "breakdown": rating.breakdown,
            }
        )
    return output
