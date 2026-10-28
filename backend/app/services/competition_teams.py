"""Registered competition teams; CompetitionApplication is the admitted roster projection."""

from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from app.models import *
from app.schemas import ResultIn
from app.services.common import require, own, can_athlete
from app.services.age_groups import age_check, age_error


def members(db, team_id):
    return db.scalars(
        select(CompetitionTeamMember)
        .where(CompetitionTeamMember.team_id == team_id)
        .order_by(CompetitionTeamMember.id)
    ).all()


def manager(db, actor, team):
    if actor.role == "athlete":
        return own(db, Athlete, actor).id == team.captain_id
    if actor.role == "coach":
        coach = own(db, Coach, actor)
        return not coach.archived_at and actor.user.id == team.created_by
    return False


def require_manager(db, actor, team):
    if not manager(db, actor, team):
        raise HTTPException(
            403, "Управлять командой может капитан или создавший её тренер"
        )


def check_athlete(db, comp, athlete_id):
    athlete = require(db, Athlete, athlete_id)
    if not any(r.id == "athlete" for r in athlete.user.roles):
        raise HTTPException(422, "У участника нет роли спортсмена")
    if athlete.suspended_until and athlete.suspended_until >= date.today():
        raise HTTPException(422, f"{athlete.user.full_name}: действует отстранение")
    check = age_check(db, comp, athlete)
    if not check["eligible"]:
        raise HTTPException(422, f"{athlete.user.full_name}: {age_error(check)}")
    enrollment = db.get(AthleteDiscipline, (athlete.id, comp.discipline_id))
    if (
        not enrollment
        or enrollment.start_year > comp.start_date.year
        or (
            enrollment.end_year is not None
            and enrollment.end_year < comp.start_date.year
        )
    ):
        raise HTTPException(
            422, f"{athlete.user.full_name}: нет действующей дисциплины в профиле"
        )
    return athlete, check


def check_roster(db, comp, team, actor=None):
    roster = members(db, team.id)
    if not comp.team_min <= len(roster) <= comp.team_max:
        raise HTTPException(
            422, f"Нужен состав от {comp.team_min} до {comp.team_max} участников"
        )
    if any(m.status != "accepted" for m in roster):
        raise HTTPException(
            422, "Все участники должны подтвердить приглашения; удалите отклонённые"
        )
    if team.captain_id not in {m.athlete_id for m in roster}:
        raise HTTPException(422, "Капитан должен входить в подтверждённый состав")
    for m in roster:
        check_athlete(db, comp, m.athlete_id)
        if actor and actor.role == "coach":
            can_athlete(db, actor, m.athlete_id, comp.discipline_id)
    return roster


def expand_results(db, comp, data, partial=False):
    if comp.entry_mode != "team":
        if data.team_results:
            raise HTTPException(422, "Для личного зачёта нужны результаты спортсменов")
        return data.results
    if data.results:
        raise HTTPException(
            422, "В командном зачёте результат вводится один раз на допущенную команду"
        )
    teams = {
        t.id: t
        for t in db.scalars(
            select(CompetitionTeam).where(
                CompetitionTeam.competition_id == comp.id,
                CompetitionTeam.status == "approved",
            )
        )
    }
    ids = [r.team_id for r in data.team_results]
    if (
        not set(ids) <= set(teams)
        or not partial and set(ids) != set(teams)
        or len(ids) != len(set(ids))
    ):
        raise HTTPException(422, "Нужен один результат для каждой допущенной команды")
    results = []
    for r in data.team_results:
        team = teams[r.team_id]
        # Eligibility was checked at admission. Roster is frozen; later suspension
        # affects rating separately, rather than making historical correction impossible.
        roster = members(db, team.id)
        if any(m.status != "accepted" for m in roster):
            raise HTTPException(409, "Нарушен подтверждённый состав команды")
        results.extend(
            ResultIn(
                athlete_id=m.athlete_id,
                place=r.place,
                score=r.score,
                team_name=team.name,
            )
            for m in roster
        )
    return results
