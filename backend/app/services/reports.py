from collections import defaultdict
from datetime import date
from sqlalchemy import select
from app.models import *
from app.services.common import age_at


def population(
    db,
    start_year,
    end_year,
    organization_id=None,
    discipline_id=None,
    municipality="",
    min_age=0,
    max_age=100,
):
    counts = defaultdict(set)
    history = defaultdict(list)
    for period in db.scalars(select(AthleteOrganization)):
        history[period.athlete_id].append(period)

    def organization_in(athlete_id, year):
        # The latest period touching the year: a transfer moves the athlete
        # to the new organization for the whole year of the transfer.
        periods = [
            p
            for p in history[athlete_id]
            if p.start_date.year <= year
            and (p.end_date is None or p.end_date.year >= year)
        ]
        if not periods:
            return None
        return max(periods, key=lambda p: p.start_date).organization_id

    for enrollment, athlete in db.execute(
        select(AthleteDiscipline, Athlete).join(
            Athlete, Athlete.id == AthleteDiscipline.athlete_id
        )
    ):
        if (
            discipline_id
            and enrollment.discipline_id != discipline_id
            or municipality.lower() not in athlete.municipality.lower()
        ):
            continue
        for year in range(start_year, end_year + 1):
            if not enrollment.start_year <= year <= (enrollment.end_year or end_year):
                continue
            org_id = organization_in(athlete.id, year)
            if organization_id and org_id != organization_id:
                continue
            org = db.get(Organization, org_id) if org_id else None
            age = age_at(athlete.user.birth_date, date(year, 12, 31))
            if not min_age <= age <= max_age:
                continue
            group = (
                "До 14 лет"
                if age < 14
                else "14–17 лет"
                if age < 18
                else "18 лет и старше"
            )
            key = (
                year,
                org.name if org else "Без организации",
                db.get(Discipline, enrollment.discipline_id).short_name,
                group,
                athlete.municipality,
            )
            counts[key].add(athlete.id)
    rows = [[*key, len(ids)] for key, ids in sorted(counts.items())]
    totals = []
    for year in range(start_year, end_year + 1):
        unique = set().union(*(ids for key, ids in counts.items() if key[0] == year))
        totals.append({"year": year, "count": len(unique)})
    return {
        "totals": totals,
        "rows": rows,
        "headers": [
            "Год",
            "Организация",
            "Дисциплина",
            "Возрастная группа",
            "Муниципалитет",
            "Численность",
        ],
        "source": "Годы начала и окончания занятий из реестра; организация — по истории переходов (в год перехода — новая). Возраст на 31 декабря; в итогах спортсмен считается один раз.",
    }

