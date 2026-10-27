from collections import defaultdict
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.services.glossary import CATEGORIES, LEVELS, glossary_terms
from app.services.ratings import RANKS

router = APIRouter(prefix="/public", tags=["Публичные страницы"])

# Short descriptions for newcomers, keyed by Discipline.short_name.
ABOUT = {
    "Алгоритмы": "Олимпиадные задачи на время: алгоритмы, структуры данных, математика.",
    "Продуктовая разработка": "Командная разработка готового продукта по заданию за ограниченное время.",
    "Информационная безопасность": "Соревнования CTF: поиск уязвимостей, защита и анализ систем.",
    "Искусственный интеллект": "Модели машинного обучения и анализ данных на реальных задачах.",
    "Робототехника": "Программирование роботов, которые проходят трассы и выполняют задания.",
    "Беспилотные системы": "Программирование дронов: автономные полёты и миссии.",
}


@router.get("/navigator")
def navigator(db: Session = Depends(get_db)):
    """Public newcomer guide: no personal data, only aggregates and published events."""
    today = date.today()
    disciplines = db.scalars(select(Discipline).order_by(Discipline.id)).all()
    orgs = {o.id: o for o in db.scalars(select(Organization))}
    # organization -> discipline -> ids of active coaches / athletes
    coaches = defaultdict(lambda: defaultdict(set))
    athletes = defaultdict(lambda: defaultdict(set))
    for coach_id, coach_org, discipline_id in db.execute(
        select(Coach.id, Coach.organization_id, CoachDiscipline.discipline_id)
        .join(CoachDiscipline, CoachDiscipline.coach_id == Coach.id)
        .where(Coach.archived_at.is_(None), Coach.organization_id.is_not(None))
    ):
        coaches[coach_org][discipline_id].add(coach_id)
    for athlete_id, athlete_org, discipline_id in db.execute(
        select(Athlete.id, Athlete.organization_id, AthleteDiscipline.discipline_id)
        .join(AthleteDiscipline, AthleteDiscipline.athlete_id == Athlete.id)
        .where(
            Athlete.organization_id.is_not(None), AthleteDiscipline.end_year.is_(None)
        )
    ):
        athletes[athlete_org][discipline_id].add(athlete_id)

    places = []
    for org_id in sorted(set(coaches) | set(athletes), key=lambda i: orgs[i].name):
        org = orgs[org_id]
        ids = set(coaches[org_id]) | set(athletes[org_id])
        places.append(
            {
                "id": org.id,
                "name": org.name,
                "kind": org.kind,
                "municipality": org.municipality,
                "discipline_ids": sorted(ids),
                "coaches": len(set().union(*coaches[org_id].values())),
                "athletes": len(set().union(*athletes[org_id].values())),
            }
        )

    upcoming = db.scalars(
        select(Competition)
        .where(Competition.state != "draft", Competition.end_date >= today)
        .order_by(Competition.start_date)
        .limit(12)
    ).all()
    return {
        "disciplines": [
            {
                "id": d.id,
                "name": d.name,
                "short_name": d.short_name,
                "about": ABOUT.get(d.short_name, ""),
                "organizations": sum(d.id in p["discipline_ids"] for p in places),
                "upcoming": sum(c.discipline_id == d.id for c in upcoming),
            }
            for d in disciplines
        ],
        "municipalities": sorted({p["municipality"] for p in places}),
        "places": places,
        "competitions": [
            {
                "id": c.id,
                "title": c.title,
                "discipline_id": c.discipline_id,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "deadline": c.deadline,
                "location": c.location,
                "format": c.format,
                "min_age": c.min_age,
                "max_age": c.max_age,
                "registration_open": c.state == "open" and c.deadline >= today,
            }
            for c in upcoming
        ],
    }


@router.get("/glossary")
def glossary(db: Session = Depends(get_db)):
    """Terms plus the rules the platform already uses: rank ladder, rating, EVSK."""
    disciplines = {d.id: d.short_name for d in db.scalars(select(Discipline))}
    rules = {r.level: r for r in db.scalars(select(RatingRule))}
    evsk = db.scalars(select(EvskRule)).all()
    order = {name: i for i, name in enumerate(RANKS)}
    return {
        "categories": CATEGORIES,
        "terms": glossary_terms(),
        "ladder": RANKS,
        "levels": [
            {
                "id": key,
                "name": name,
                "points": [rules[key].first, rules[key].second, rules[key].third]
                if key in rules
                else None,
            }
            for key, name in LEVELS.items()
        ],
        "evsk": [
            {
                "id": r.id,
                "discipline_id": r.discipline_id,
                "discipline": disciplines.get(r.discipline_id),
                "rank": r.rank_name,
                "level": r.level,
                "level_name": LEVELS.get(r.level, r.level),
                "max_place": r.max_place,
                "min_participants": r.min_participants,
                "source": r.source,
            }
            for r in sorted(
                evsk,
                key=lambda r: (r.discipline_id, order.get(r.rank_name, len(RANKS))),
            )
        ],
    }
