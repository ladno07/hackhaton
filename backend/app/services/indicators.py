"""Development indicators: calculated from the registry (each with a description
of where the number comes from) and entered by the federation with a source
and supporting documents."""

from datetime import date
from sqlalchemy import select, func
from app.models import *
from app.services.reports import population


def year_end(year):
    # for the current year the state is taken as of today
    return min(date(year, 12, 31), date.today())


def registry_indicators(db, start_year, end_year):
    years = range(start_year, end_year + 1)
    people = {t["year"]: t["count"] for t in population(db, start_year, end_year)["totals"]}

    def count(query):
        return db.scalar(select(func.count()).select_from(query.subquery()))

    def ranked(year):
        at = year_end(year)
        return count(
            select(SportsRank.athlete_id)
            .where(SportsRank.assigned_on <= at, SportsRank.expires_on >= at)
            .distinct()
        )

    def competitions(year):
        return count(
            select(Competition.id).where(
                Competition.state == "published",
                func.extract("year", Competition.end_date) == year,
            )
        )

    def participants(year):
        return count(
            select(CompetitionResult.athlete_id)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                Competition.state == "published",
                func.extract("year", Competition.end_date) == year,
            )
            .distinct()
        )

    def judges(year):
        at = year_end(year)
        return count(
            select(JudgeCategory.judge_id)
            .where(JudgeCategory.assigned_on <= at, JudgeCategory.expires_on >= at)
            .distinct()
        )

    def organizations(year):
        return count(
            select(AthleteOrganization.organization_id)
            .where(
                func.extract("year", AthleteOrganization.start_date) <= year,
                AthleteOrganization.end_date.is_(None)
                | (func.extract("year", AthleteOrganization.end_date) >= year),
            )
            .distinct()
        )

    specs = [
        (
            "population",
            "Численность занимающихся",
            "чел.",
            "Реестр спортсменов: годы занятий по дисциплинам, в итогах спортсмен считается один раз.",
            people.get,
        ),
        (
            "ranked",
            "Спортсменов с действующим разрядом",
            "чел.",
            "Реестр разрядов: разряд действует на 31 декабря (для текущего года — на сегодня).",
            ranked,
        ),
        (
            "competitions",
            "Проведено соревнований",
            "ед.",
            "Календарь: соревнования с опубликованными итогами, по дате окончания.",
            competitions,
        ),
        (
            "participants",
            "Участников соревнований",
            "чел.",
            "Итоговые протоколы опубликованных соревнований, без повторов.",
            participants,
        ),
        (
            "judges",
            "Судей с действующей категорией",
            "чел.",
            "Реестр судей: категория действует на 31 декабря (для текущего года — на сегодня).",
            judges,
        ),
        (
            "organizations",
            "Организаций с занимающимися",
            "ед.",
            "История переходов спортсменов: организации, где в году был хотя бы один спортсмен.",
            organizations,
        ),
    ]
    return [
        {
            "key": key,
            "name": name,
            "unit": unit,
            "source": source,
            "values": [{"year": y, "value": calc(y) or 0} for y in years],
        }
        for key, name, unit, source, calc in specs
    ]


def document_info(doc):
    return {
        k: getattr(doc, k) for k in ("id", "filename", "size", "content_type", "uploaded_at")
    }


def indicator_info(db, obj):
    org = db.get(Organization, obj.organization_id) if obj.organization_id else None
    return {
        "id": obj.id,
        "year": obj.year,
        "name": obj.name,
        "value": obj.value,
        "unit": obj.unit,
        "organization_id": obj.organization_id,
        "organization": org.name if org else None,
        "source": obj.source,
        "comment": obj.comment,
        "updated_at": obj.updated_at,
        "documents": [document_info(d) for d in obj.documents],
    }


def entered_indicators(db, start_year, end_year):
    return [
        indicator_info(db, obj)
        for obj in db.scalars(
            select(DevelopmentIndicator)
            .where(
                DevelopmentIndicator.year >= start_year,
                DevelopmentIndicator.year <= end_year,
            )
            .order_by(
                DevelopmentIndicator.year.desc(),
                DevelopmentIndicator.name,
                DevelopmentIndicator.id,
            )
        )
    ]


def number(value):
    return f"{value:g}".replace(".", ",")
