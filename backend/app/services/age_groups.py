from sqlalchemy import select
from app.models import *
from app.services.common import age_at


def group_age(group, born, start):
    # "year": the age the athlete reaches in the calendar year of the start
    if group.age_rule == "year":
        return start.year - born.year
    return age_at(born, start)


def competition_groups(db, comp_id):
    return db.scalars(
        select(AgeGroup)
        .join(CompetitionAgeGroup, CompetitionAgeGroup.age_group_id == AgeGroup.id)
        .where(CompetitionAgeGroup.competition_id == comp_id)
        .order_by(AgeGroup.sort_order, AgeGroup.id)
    ).all()


def group_view(group):
    return {
        k: getattr(group, k)
        for k in ("id", "name", "sex", "min_age", "max_age", "age_rule")
    }


def age_check(db, comp, athlete, groups=None):
    """Explains whether the athlete fits the competition by age and sex."""
    user = athlete.user
    groups = competition_groups(db, comp.id) if groups is None else groups
    result = {
        "age": age_at(user.birth_date, comp.start_date),
        "year_age": comp.start_date.year - user.birth_date.year,
        "sex": user.sex,
        "groups": [],
        "reason": None,
    }
    if not groups:
        result["eligible"] = comp.min_age <= result["age"] <= comp.max_age
        result["reason"] = None if result["eligible"] else "age"
        return result
    by_age = [
        g
        for g in groups
        if g.min_age <= group_age(g, user.birth_date, comp.start_date) <= g.max_age
    ]
    matched = [g for g in by_age if g.sex is None or g.sex == user.sex]
    result["groups"] = [group_view(g) for g in matched]
    result["eligible"] = bool(matched)
    if not matched:
        result["reason"] = (
            "age" if not by_age else "sex" if user.sex else "sex_missing"
        )
    return result


def age_error(check):
    if check["reason"] == "sex_missing":
        return "Укажите пол в профиле спортсмена, чтобы определить возрастную группу"
    if check["reason"] == "sex":
        return "Возрастные группы соревнования не предусматривают пол спортсмена"
    return "Спортсмен не подходит по возрасту на дату соревнования"
