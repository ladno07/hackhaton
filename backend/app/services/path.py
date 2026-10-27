"""Personal path of an athlete: rank ladder, EVSK goals and the next step."""

from datetime import date, timedelta
from sqlalchemy import func, select
from app.models import *
from app.services.age_groups import age_check
from app.services.glossary import LEVELS
from app.services.ratings import RANKS

# A held rank needs attention once its expiry is this close.
EXPIRY_DAYS = 30


def rank_index(name):
    return RANKS.index(name) if name in RANKS else None


def is_above(name, current):
    """Rules with a rank outside the ladder are always shown as goals."""
    index = rank_index(name)
    return index is None or index > rank_index(current)


def participants(db, competition_ids):
    if not competition_ids:
        return {}
    return dict(
        db.execute(
            select(CompetitionResult.competition_id, func.count())
            .where(CompetitionResult.competition_id.in_(competition_ids))
            .group_by(CompetitionResult.competition_id)
        ).all()
    )


def discipline_path(db, athlete, discipline, start_year, today):
    ranks = db.scalars(
        select(SportsRank)
        .where(
            SportsRank.athlete_id == athlete.id,
            SportsRank.discipline_id == discipline.id,
        )
        .order_by(SportsRank.assigned_on, SportsRank.id)
    ).all()
    valid = [r for r in ranks if r.expires_on >= today]
    held = max(valid, key=lambda r: rank_index(r.name) or 0, default=None)
    current = held.name if held and held.name in RANKS else RANKS[0]
    position = rank_index(current)
    next_rank = RANKS[position + 1] if position + 1 < len(RANKS) else None

    results = db.execute(
        select(CompetitionResult, Competition)
        .join(Competition, Competition.id == CompetitionResult.competition_id)
        .where(
            CompetitionResult.athlete_id == athlete.id,
            Competition.discipline_id == discipline.id,
            Competition.state == "published",
        )
        .order_by(Competition.start_date, Competition.id)
    ).all()
    counts = participants(db, [c.id for _, c in results])
    applications = db.scalars(
        select(RankApplication).where(
            RankApplication.athlete_id == athlete.id,
            RankApplication.result_id.in_([r.id for r, _ in results]),
        )
    ).all()

    goals = []
    rules = db.scalars(
        select(EvskRule)
        .where(EvskRule.discipline_id == discipline.id)
        .order_by(EvskRule.id)
    ).all()
    for rule in sorted(rules, key=lambda r: rank_index(r.rank_name) or len(RANKS)):
        if not is_above(rule.rank_name, current):
            continue
        achieved = []
        for result, comp in results:
            if (
                comp.rating_level == rule.level
                and result.place <= rule.max_place
                and counts.get(comp.id, 0) >= rule.min_participants
            ):
                application = next(
                    (
                        a
                        for a in applications
                        if a.result_id == result.id and a.name == rule.rank_name
                    ),
                    None,
                )
                achieved.append(
                    {
                        "result_id": result.id,
                        "competition_id": comp.id,
                        "title": comp.title,
                        "start_date": comp.start_date,
                        "place": result.place,
                        "participants": counts.get(comp.id, 0),
                        "application": application.status if application else None,
                    }
                )
        goals.append(
            {
                "id": rule.id,
                "rank": rule.rank_name,
                "level": rule.level,
                "max_place": rule.max_place,
                "min_participants": rule.min_participants,
                "source": rule.source,
                "achieved": achieved,
            }
        )

    levels = {g["level"] for g in goals if not g["achieved"]}
    upcoming = []
    for comp in db.scalars(
        select(Competition)
        .where(
            Competition.discipline_id == discipline.id,
            Competition.state == "open",
            Competition.deadline >= today,
        )
        .order_by(Competition.start_date, Competition.id)
    ):
        upcoming.append(
            {
                "id": comp.id,
                "title": comp.title,
                "start_date": comp.start_date,
                "deadline": comp.deadline,
                "level": comp.rating_level,
                "counts_for_goal": comp.rating_level in levels,
                "eligible": age_check(db, comp, athlete)["eligible"],
            }
        )

    return {
        "id": discipline.id,
        "name": discipline.name,
        "short_name": discipline.short_name,
        "start_year": start_year,
        "current_rank": current,
        "held": {
            "id": held.id,
            "name": held.name,
            "assigned_on": held.assigned_on,
            "expires_on": held.expires_on,
            "order_number": held.order_number,
        }
        if held
        else None,
        "next_rank": next_rank,
        "ranks": [
            {
                "id": r.id,
                "name": r.name,
                "assigned_on": r.assigned_on,
                "expires_on": r.expires_on,
                "order_number": r.order_number,
                "valid": r.expires_on >= today,
            }
            for r in ranks
        ],
        "stats": {
            "performances": len(results),
            "podiums": sum(r.place <= 3 for r, _ in results),
            "best_place": min((r.place for r, _ in results), default=None),
        },
        "goals": goals,
        "upcoming": upcoming,
        "next_step": next_step(held, goals, upcoming, today),
        "timeline": timeline(start_year, results, ranks),
    }


def next_step(held, goals, upcoming, today):
    """One recommendation, the most urgent first."""
    if held and held.expires_on <= today + timedelta(days=EXPIRY_DAYS):
        return {
            "kind": "confirm",
            "text": f"Разряд «{held.name}» действует до {held.expires_on:%d.%m.%Y}. "
            "Подтвердите его результатом на соревнованиях.",
        }
    # Goals up to the highest one already applied for are no longer worth it.
    claimed = max(
        (
            i
            for i, g in enumerate(goals)
            if any(a["application"] in ("pending", "approved") for a in g["achieved"])
        ),
        default=-1,
    )
    for goal in reversed(goals[claimed + 1 :]):
        ready = [a for a in goal["achieved"] if a["application"] is None]
        if ready:
            return {
                "kind": "apply",
                "text": f"Результат «{ready[0]['title']}» соответствует условию "
                f"для разряда «{goal['rank']}». Подайте заявку на присвоение.",
                "result_id": ready[0]["result_id"],
                "rank": goal["rank"],
            }
    if claimed >= 0 and any(
        a["application"] == "pending" for a in goals[claimed]["achieved"]
    ):
        return {
            "kind": "wait",
            "text": f"Заявка на разряд «{goals[claimed]['rank']}» "
            "на рассмотрении федерации.",
        }
    remaining = [g for g in goals[claimed + 1 :] if not g["achieved"]]
    if remaining:
        goal = remaining[0]
        suitable = [c for c in upcoming if c["level"] == goal["level"] and c["eligible"]]
        text = (
            f"Для разряда «{goal['rank']}» займите место не ниже {goal['max_place']}-го "
            f"на соревновании уровня «{LEVELS.get(goal['level'], goal['level'])}» "
            f"при числе участников от {goal['min_participants']}."
        )
        if suitable:
            text += f" Ближайший подходящий старт: «{suitable[0]['title']}»."
        return {"kind": "compete", "text": text}
    if goals:
        return {
            "kind": "none",
            "text": "Все внесённые условия ЕВСК выполнены. Выступайте на "
            "соревнованиях и следите за рейтингом.",
        }
    return {
        "kind": "none",
        "text": "Федерация ещё не внесла условия ЕВСК для следующего разряда "
        "в этой дисциплине. Выступайте на соревнованиях и следите за рейтингом.",
    }


def timeline(start_year, results, ranks):
    events = [
        {
            "date": date(start_year, 1, 1),
            "kind": "start",
            "title": "Начало занятий дисциплиной",
        }
    ]
    events += [
        {
            "date": comp.start_date,
            "kind": "result",
            "title": comp.title,
            "place": result.place,
            "competition_id": comp.id,
        }
        for result, comp in results
    ]
    events += [
        {
            "date": r.assigned_on,
            "kind": "rank",
            "title": f"Присвоен разряд «{r.name}»",
            "order_number": r.order_number,
        }
        for r in ranks
    ]
    return sorted(events, key=lambda e: (e["date"], e["kind"] != "start"))


def personal_path(db, athlete):
    today = date.today()
    disciplines = db.execute(
        select(AthleteDiscipline, Discipline)
        .join(Discipline, Discipline.id == AthleteDiscipline.discipline_id)
        .where(
            AthleteDiscipline.athlete_id == athlete.id,
            AthleteDiscipline.end_year.is_(None),
        )
        .order_by(Discipline.id)
    ).all()
    paths = [
        discipline_path(db, athlete, d, link.start_year, today)
        for link, d in disciplines
    ]
    organizations = {o.id: o.name for o in db.scalars(select(Organization))}
    return {
        "athlete": {
            "id": athlete.id,
            "full_name": athlete.user.full_name,
            "training_stage": athlete.training_stage,
            "organization": organizations.get(athlete.organization_id),
        },
        "ladder": RANKS,
        "summary": {
            "disciplines": len(paths),
            "ranks": sum(p["held"] is not None for p in paths),
            # goals with a matching result that has no application yet
            "ready_to_apply": sum(
                any(a["application"] is None for a in g["achieved"])
                for p in paths
                for g in p["goals"]
            ),
            "to_confirm": sum(p["next_step"]["kind"] == "confirm" for p in paths),
        },
        "disciplines": paths,
    }
