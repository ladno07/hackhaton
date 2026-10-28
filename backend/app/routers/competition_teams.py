from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import (
    TeamCreateIn,
    TeamMemberIn,
    TeamResponseIn,
    TeamReviewIn,
    TeamReopenIn,
)
from app.security import Actor, current_actor, allow
from app.services.common import row, require, own, can_athlete, active_card, audit
from app.services.competition_teams import (
    members,
    manager,
    require_manager,
    check_roster,
    check_athlete,
)
from app.services.notifications import notify, admins
from app.services.athlete_ids import public_athlete_id, parse_athlete_id, candidate_view
from app.routers.competitions import locked
from app.services import integrations

router = APIRouter(tags=["Команды соревнований"])


def competition(db, comp_id, actor, edit=False):
    comp = locked(db, comp_id)
    if comp.state == "draft" and actor.role != "admin":
        raise HTTPException(404, "Соревнование не найдено")
    if comp.entry_mode != "team":
        raise HTTPException(409, "Это соревнование с личным зачётом")
    if edit and (comp.state != "open" or comp.deadline < date.today()):
        raise HTTPException(409, "Приём команд и изменений закрыт")
    return comp


def get_team(db, comp_id, team_id):
    team = require(db, CompetitionTeam, team_id)
    if team.competition_id != comp_id:
        raise HTTPException(404, "Команда не найдена в соревновании")
    return team


def name_exists(db, comp_id, name, except_id=None):
    return any(
        t.id != except_id and t.name.casefold() == name.casefold()
        for t in db.scalars(
            select(CompetitionTeam).where(CompetitionTeam.competition_id == comp_id)
        )
    )


def editable(team):
    if team.status not in {"draft", "returned"}:
        raise HTTPException(
            409, "Состав зафиксирован. Сначала верните заявку на редактирование"
        )


def event(db, actor, team, action, details=None, audience=None):
    team.revision += 1
    audit(db, actor, action, team, details)
    ids = (
        audience
        if audience is not None
        else [
            team.created_by,
            *[db.get(Athlete, m.athlete_id).user_id for m in members(db, team.id)],
        ]
    )
    comp = db.get(Competition, team.competition_id)
    notify(
        db,
        ids,
        action,
        f"{comp.title} · {team.name}. {team.comment} Откройте соревнование → Команды.",
        f"competition-team:{comp.id}:{team.id}:{team.revision}",
    )


def view(db, actor, team):
    roster = members(db, team.id)
    detailed = (
        actor.role == "admin"
        or manager(db, actor, team)
        or any(db.get(Athlete, m.athlete_id).user_id == actor.user.id for m in roster)
    )
    # Other users see admitted teams only; no pending invitation lists.
    return {
        **row(team),
        "captain": db.get(Athlete, team.captain_id).user.full_name,
        "can_manage": manager(db, actor, team),
        "members": [
            {
                **row(m),
                "full_name": db.get(Athlete, m.athlete_id).user.full_name,
                "public_id": public_athlete_id(m.athlete_id),
                "is_me": actor.role == "athlete"
                and db.get(Athlete, m.athlete_id).user_id == actor.user.id,
            }
            for m in roster
        ],
        "comment": team.comment if detailed else "",
    }


@router.get("/competitions/{comp_id}/teams")
def list_teams(
    comp_id: int, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    competition(db, comp_id, actor)
    output = []
    for team in db.scalars(
        select(CompetitionTeam)
        .where(CompetitionTeam.competition_id == comp_id)
        .order_by(CompetitionTeam.id)
    ):
        member = any(
            db.get(Athlete, m.athlete_id).user_id == actor.user.id
            for m in members(db, team.id)
        )
        if (
            actor.role == "admin"
            or team.status == "approved"
            or manager(db, actor, team)
            or (actor.role == "athlete" and member)
        ):
            output.append(view(db, actor, team))
    return output


@router.get("/competitions/{comp_id}/team-candidates")
def candidates(
    comp_id: int,
    q: str | None = Query(None, min_length=2, max_length=200),
    public_id: str | None = Query(None, min_length=10, max_length=14),
    mine: bool = False,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = competition(db, comp_id, actor, edit=True)
    if sum([q is not None, public_id is not None, mine]) != 1:
        raise HTTPException(422, "Выберите поиск по ID, ФИО или список подопечных")
    if mine and actor.role != "coach":
        raise HTTPException(403, "Список подопечных доступен тренеру")
    if actor.role == "coach":
        active_card(db, Coach, actor)
    if q is not None and len(q.strip()) < 2:
        raise HTTPException(422, "Введите не менее двух символов ФИО")
    query = select(Athlete).order_by(Athlete.id)
    if public_id is not None:
        query = query.where(Athlete.id == parse_athlete_id(public_id))
    output = []
    for athlete in db.scalars(query):
        if not any(r.id == "athlete" for r in athlete.user.roles):
            continue
        if (
            q is not None
            and q.strip().casefold() not in athlete.user.full_name.casefold()
        ):
            continue
        if actor.role == "coach":
            try:
                can_athlete(db, actor, athlete.id, comp.discipline_id)
            except HTTPException:
                continue
        output.append(candidate_view(db, athlete))
        if not mine and len(output) == 30:
            break
    return output


@router.post("/competitions/{comp_id}/teams", status_code=201)
def create_team(
    comp_id: int,
    data: TeamCreateIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = competition(db, comp_id, actor, edit=True)
    if actor.role == "coach":
        active_card(db, Coach, actor)
    captain = can_athlete(db, actor, data.captain_id, comp.discipline_id)
    if name_exists(db, comp_id, data.name):
        raise HTTPException(409, "Название команды уже занято")
    if actor.role == "athlete" and db.scalar(
        select(CompetitionTeamMember.id).where(
            CompetitionTeamMember.competition_id == comp_id,
            CompetitionTeamMember.athlete_id == captain.id,
            CompetitionTeamMember.status == "accepted",
        )
    ):
        raise HTTPException(409, "Вы уже подтвердили участие в другой команде")
    team = CompetitionTeam(
        competition_id=comp_id,
        name=data.name,
        captain_id=captain.id,
        created_by=actor.user.id,
    )
    db.add(team)
    db.flush()
    db.add(
        CompetitionTeamMember(
            team_id=team.id,
            competition_id=comp.id,
            athlete_id=captain.id,
            status="accepted" if actor.role == "athlete" else "invited",
            responded_at=now() if actor.role == "athlete" else None,
        )
    )
    event(db, actor, team, "Создана команда и приглашён капитан")
    return view(db, actor, team)


@router.put("/competitions/{comp_id}/teams/{team_id}")
def edit_team(
    comp_id: int,
    team_id: int,
    data: TeamCreateIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    require_manager(db, actor, team)
    editable(team)
    if data.captain_id not in {m.athlete_id for m in members(db, team_id)}:
        raise HTTPException(422, "Сначала пригласите будущего капитана в команду")
    if name_exists(db, comp_id, data.name, team_id):
        raise HTTPException(409, "Название команды уже занято")
    team.name, team.captain_id = data.name, data.captain_id
    event(db, actor, team, "Изменены название или капитан команды", data.model_dump())
    return view(db, actor, team)


@router.post("/competitions/{comp_id}/teams/{team_id}/members", status_code=201)
def invite(
    comp_id: int,
    team_id: int,
    data: TeamMemberIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    require_manager(db, actor, team)
    editable(team)
    athlete_id = (
        parse_athlete_id(data.public_id)
        if data.public_id is not None
        else data.athlete_id
    )
    athlete = require(db, Athlete, athlete_id)
    if not any(r.id == "athlete" for r in athlete.user.roles):
        raise HTTPException(422, "Участнику нужна роль спортсмена")
    if actor.role == "coach":
        can_athlete(db, actor, athlete.id, comp.discipline_id)
    roster = members(db, team_id)
    if len(roster) >= comp.team_max:
        raise HTTPException(422, "Достигнут максимальный размер команды")
    if any(m.athlete_id == athlete.id for m in roster):
        raise HTTPException(
            409, "Спортсмен уже приглашён; для повторного приглашения удалите прежнее"
        )
    if db.scalar(
        select(CompetitionTeamMember.id).where(
            CompetitionTeamMember.competition_id == comp_id,
            CompetitionTeamMember.athlete_id == athlete.id,
            CompetitionTeamMember.status == "accepted",
        )
    ):
        raise HTTPException(409, "Спортсмен уже подтвердил другую команду")
    db.add(
        CompetitionTeamMember(
            team_id=team_id, competition_id=comp_id, athlete_id=athlete.id
        )
    )
    event(db, actor, team, "Приглашение в команду", data.model_dump())
    return view(db, actor, team)


@router.patch("/competitions/{comp_id}/teams/{team_id}/response")
def respond(
    comp_id: int,
    team_id: int,
    data: TeamResponseIn,
    actor: Actor = Depends(allow("athlete")),
    db: Session = Depends(get_db),
):
    competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    if team.status == "approved":
        raise HTTPException(
            409,
            "Состав допущен. Сначала запросите возврат на редактирование у капитана или тренера",
        )
    athlete = own(db, Athlete, actor)
    member = next((m for m in members(db, team_id) if m.athlete_id == athlete.id), None)
    if not member:
        raise HTTPException(403, "Вас не приглашали в команду")
    if member.status == data.status:
        return view(db, actor, team)
    if (
        member.athlete_id == team.captain_id
        and member.status == "accepted"
        and data.status == "declined"
    ):
        raise HTTPException(
            409, "Перед выходом передайте капитанство другому участнику"
        )
    if data.status == "accepted" and member.status != "invited":
        raise HTTPException(409, "Нужно новое приглашение капитана или тренера")
    if data.status == "accepted" and db.scalar(
        select(CompetitionTeamMember.id).where(
            CompetitionTeamMember.competition_id == comp_id,
            CompetitionTeamMember.athlete_id == athlete.id,
            CompetitionTeamMember.status == "accepted",
            CompetitionTeamMember.id != member.id,
        )
    ):
        raise HTTPException(409, "Можно подтвердить только одну команду в соревновании")
    member.status, member.responded_at = data.status, now()
    if team.status == "pending":
        team.status, team.comment = (
            "returned",
            "Участник отозвал согласие. Нужна повторная подача заявки",
        )
    event(
        db,
        actor,
        team,
        "Ответ на приглашение в команду",
        {"athlete_id": athlete.id, **data.model_dump()},
    )
    return view(db, actor, team)


@router.delete(
    "/competitions/{comp_id}/teams/{team_id}/members/{athlete_id}", status_code=204
)
def remove_member(
    comp_id: int,
    team_id: int,
    athlete_id: int,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    require_manager(db, actor, team)
    editable(team)
    if athlete_id == team.captain_id:
        raise HTTPException(409, "Сначала назначьте другого капитана")
    member = next((m for m in members(db, team_id) if m.athlete_id == athlete_id), None)
    if not member:
        raise HTTPException(404, "Участник не найден")
    db.delete(member)
    event(db, actor, team, "Участник исключён из команды", {"athlete_id": athlete_id})


@router.post("/competitions/{comp_id}/teams/{team_id}/submit")
def submit(
    comp_id: int,
    team_id: int,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    comp = competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    require_manager(db, actor, team)
    editable(team)
    check_roster(db, comp, team, actor)
    team.status, team.comment = "pending", ""
    event(
        db,
        actor,
        team,
        "Командная заявка подана",
        audience=[
            *admins(db),
            team.created_by,
            *[db.get(Athlete, m.athlete_id).user_id for m in members(db, team_id)],
        ],
    )
    return view(db, actor, team)


@router.post("/competitions/{comp_id}/teams/{team_id}/reopen")
def reopen(
    comp_id: int,
    team_id: int,
    data: TeamReopenIn,
    actor: Actor = Depends(allow("athlete", "coach", "admin")),
    db: Session = Depends(get_db),
):
    comp = competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    if actor.role != "admin":
        require_manager(db, actor, team)
    if team.status not in {"approved", "pending"}:
        raise HTTPException(409, "Заявка уже доступна для редактирования")
    for member in members(db, team_id):
        application = db.scalar(
            select(CompetitionApplication).where(
                CompetitionApplication.competition_id == comp_id,
                CompetitionApplication.athlete_id == member.athlete_id,
            )
        )
        if application:
            application.status, application.comment = (
                "rejected",
                "Допуск команды снят: " + data.reason,
            )
    team.status, team.comment = "returned", data.reason
    event(
        db,
        actor,
        team,
        "Командная заявка возвращена на редактирование",
        data.model_dump(),
        audience=[
            *admins(db),
            team.created_by,
            *[db.get(Athlete, m.athlete_id).user_id for m in members(db, team_id)],
        ],
    )
    return view(db, actor, team)


@router.patch("/competitions/{comp_id}/teams/{team_id}/review")
def review(
    comp_id: int,
    team_id: int,
    data: TeamReviewIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    comp = competition(db, comp_id, actor)
    team = get_team(db, comp_id, team_id)
    if comp.state not in {"open", "closed"} or team.status != "pending":
        raise HTTPException(
            409, "Заявка уже рассмотрена или соревнование не допускает модерацию"
        )
    if data.status == "returned" and len(data.comment.strip()) < 5:
        raise HTTPException(422, "Укажите причину возврата (не менее 5 символов)")
    approved = []
    if data.status == "approved":
        for member in check_roster(db, comp, team):
            _, check = check_athlete(db, comp, member.athlete_id)
            obj = db.scalar(
                select(CompetitionApplication).where(
                    CompetitionApplication.competition_id == comp_id,
                    CompetitionApplication.athlete_id == member.athlete_id,
                )
            )
            if not obj:
                obj = CompetitionApplication(
                    competition_id=comp_id,
                    athlete_id=member.athlete_id,
                    submitted_by=team.created_by,
                )
                db.add(obj)
            obj.status, obj.comment = "approved", "Допущена команда «" + team.name + "»"
            obj.approved_at = now()
            obj.age_group_id = check["groups"][0]["id"] if check["groups"] else None
            approved.append(obj)
    team.status, team.comment = data.status, data.comment
    for obj in approved:
        integrations.application_approved(db, obj, comp)
    event(db, actor, team, "Решение по командной заявке", data.model_dump())
    return view(db, actor, team)


@router.post("/competitions/{comp_id}/teams/{team_id}/cancel")
def cancel(
    comp_id: int,
    team_id: int,
    data: TeamReopenIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    competition(db, comp_id, actor, edit=True)
    team = get_team(db, comp_id, team_id)
    require_manager(db, actor, team)
    editable(team)
    for member in members(db, team_id):
        member.status, member.responded_at = "declined", now()
    team.status, team.comment = "cancelled", data.reason
    event(db, actor, team, "Команда снята с соревнования", data.model_dump())
    return view(db, actor, team)
