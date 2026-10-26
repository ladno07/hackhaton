from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import RankIn, RankDecision, TeamIn, RuleIn, Level, EvskIn, DeadlineIn
from app.security import Actor, current_actor, allow
from app.services.common import *
from app.services.notifications import (
    notify,
    admins,
    athlete_audience,
    deadlines,
    visible_in_role,
)
from app.services.ratings import ranking, RANKS

router = APIRouter(tags=["Федерация"])


@router.get("/rank-applications")
def rank_applications(
    actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    query = select(RankApplication).order_by(RankApplication.id.desc())
    if actor.role == "judge":
        query = query.where(RankApplication.judge_id == own(db, Judge, actor).id)
    elif actor.role != "admin":
        query = query.where(RankApplication.athlete_id.in_(visible_athletes(db, actor)))
    return [
        {
            **row(x),
            "full_name": db.get(Athlete, x.athlete_id).user.full_name
            if x.athlete_id
            else db.get(Judge, x.judge_id).user.full_name,
        }
        for x in db.scalars(query)
    ]


@router.post("/rank-applications", status_code=201)
def apply_rank(
    data: RankIn,
    actor: Actor = Depends(allow("athlete", "coach", "judge")),
    db: Session = Depends(get_db),
):
    values = {"name": data.name, "kind": data.kind, "submitted_by": actor.user.id}
    if actor.role == "judge":
        if data.athlete_id or data.result_id:
            raise HTTPException(
                422, "Для судейской категории результат спортсмена не указывается"
            )
        values["judge_id"] = own(db, Judge, actor).id
    else:
        if data.name not in RANKS[1:]:
            raise HTTPException(422, "Выберите разряд из справочника")
        result = (
            require(db, CompetitionResult, data.result_id) if data.result_id else None
        )
        if not result or result.athlete_id != data.athlete_id:
            raise HTTPException(422, "Выберите результат этого спортсмена")
        comp = require(db, Competition, result.competition_id)
        athlete = can_athlete(db, actor, data.athlete_id, comp.discipline_id)
        if actor.role == "athlete" and db.scalar(
            select(AthleteCoach).where(
                AthleteCoach.athlete_id == athlete.id,
                AthleteCoach.discipline_id == comp.discipline_id,
                AthleteCoach.status == "active",
            )
        ):
            raise HTTPException(409, "Заявку по этой дисциплине подаёт ваш тренер")
        values.update(athlete_id=athlete.id, result_id=result.id)
    duplicate = select(RankApplication).where(
        RankApplication.status == "pending", RankApplication.name == data.name
    )
    duplicate = (
        duplicate.where(RankApplication.judge_id == values["judge_id"])
        if "judge_id" in values
        else duplicate.where(
            RankApplication.athlete_id == values["athlete_id"],
            RankApplication.result_id == values["result_id"],
        )
    )
    if db.scalar(duplicate):
        raise HTTPException(409, "Такая заявка уже рассматривается")
    obj = RankApplication(**values)
    db.add(obj)
    audit(db, actor, "Подача заявки на разряд или категорию", obj)
    notify(
        db,
        admins(db),
        "Новая заявка на разряд / категорию",
        data.name,
        f"rank-application:{obj.id}",
    )
    return row(obj)


@router.patch("/rank-applications/{application_id}")
def decide_rank(
    application_id: int,
    data: RankDecision,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = db.scalar(
        select(RankApplication)
        .where(RankApplication.id == application_id)
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Заявка не найдена")
    if obj.status != "pending":
        raise HTTPException(409, "Заявка уже рассмотрена")
    obj.status, obj.comment = data.status, data.comment
    if data.status == "approved":
        values = {
            "name": obj.name,
            "assigned_on": data.assigned_on,
            "expires_on": data.expires_on,
            "order_number": data.order_number,
        }
        if obj.athlete_id:
            result = require(db, CompetitionResult, obj.result_id)
            comp = db.get(Competition, result.competition_id)
            db.add(
                SportsRank(
                    athlete_id=obj.athlete_id,
                    discipline_id=comp.discipline_id,
                    result_id=result.id,
                    **values,
                )
            )
        else:
            db.add(JudgeCategory(judge_id=obj.judge_id, **values))
    audit(
        db,
        actor,
        "Рассмотрение заявки на разряд / категорию",
        obj,
        data.model_dump(mode="json"),
    )
    audience = (
        athlete_audience(db, obj.athlete_id)
        if obj.athlete_id
        else [db.get(Judge, obj.judge_id).user_id]
    )
    notify(
        db,
        audience,
        "Заявка на разряд / категорию рассмотрена",
        f"{obj.name}: {obj.status}. {obj.comment}",
        f"rank-decision:{obj.id}",
    )
    return row(obj)


@router.get("/ranks")
def ranks(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    ids = visible_athletes(db, actor)
    sports = [
        {**row(r), "full_name": db.get(Athlete, r.athlete_id).user.full_name}
        for r in db.scalars(select(SportsRank).where(SportsRank.athlete_id.in_(ids)))
    ]
    cats = select(JudgeCategory)
    if actor.role == "judge":
        cats = cats.where(JudgeCategory.judge_id == own(db, Judge, actor).id)
    elif actor.role != "admin":
        return {"sports": sports, "categories": []}
    return {
        "sports": sports,
        "categories": [
            {**row(c), "full_name": db.get(Judge, c.judge_id).user.full_name}
            for c in db.scalars(cats)
        ],
    }


@router.get("/ratings")
def ratings(
    season: int = Query(date.today().year, ge=2000, le=2100),
    discipline_id: int | None = None,
    min_age: int = 0,
    max_age: int = 100,
    min_rank: str | None = None,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    if min_rank and min_rank not in RANKS:
        raise HTTPException(422, "Неизвестный разряд")
    return ranking(db, season, discipline_id, min_age, max_age, min_rank)


@router.get("/rating-rules")
def rules(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return [row(x) for x in db.scalars(select(RatingRule))]


@router.put("/rating-rules/{level}")
def edit_rules(
    level: Level,
    data: RuleIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, RatingRule, level)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    audit(
        db,
        actor,
        "Изменение правил рейтинга",
        obj,
        {"level": level, **data.model_dump()},
    )
    return row(obj)


@router.get("/team")
def team(
    season: int = date.today().year,
    discipline_id: int | None = None,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    query = select(TeamMember).where(TeamMember.season == season)
    if discipline_id:
        query = query.where(TeamMember.discipline_id == discipline_id)
    return [
        {
            **row(t),
            "full_name": db.get(Athlete, t.athlete_id).user.full_name,
            "eligible": not (
                db.get(Athlete, t.athlete_id).suspended_until
                and db.get(Athlete, t.athlete_id).suspended_until >= date.today()
            ),
        }
        for t in db.scalars(query)
    ]


@router.put("/team")
def set_team(
    data: TeamIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    require(db, Discipline, data.discipline_id)
    available = {r["athlete_id"] for r in ranking(db, data.season, data.discipline_id)}
    if not set(data.athlete_ids).issubset(available) or len(
        set(data.athlete_ids)
    ) != len(data.athlete_ids):
        raise HTTPException(
            422, "Включайте уникальных спортсменов из действующего рейтинга"
        )
    db.execute(
        delete(TeamMember).where(
            TeamMember.season == data.season,
            TeamMember.discipline_id == data.discipline_id,
        )
    )
    db.add_all(
        [
            TeamMember(
                season=data.season,
                discipline_id=data.discipline_id,
                athlete_id=i,
                selected_by=actor.user.id,
            )
            for i in data.athlete_ids
        ]
    )
    audit(db, actor, "Формирование сборной", actor.user, data.model_dump())
    return {"count": len(data.athlete_ids)}


@router.get("/evsk-rules")
def evsk_rules(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return [row(x) for x in db.scalars(select(EvskRule))]


@router.post("/evsk-rules", status_code=201)
def add_evsk(
    data: EvskIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    require(db, Discipline, data.discipline_id)
    obj = EvskRule(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Добавление условия подсветки ЕВСК", obj)
    return row(obj)


@router.delete("/evsk-rules/{rule_id}", status_code=204)
def delete_evsk(
    rule_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = require(db, EvskRule, rule_id)
    audit(db, actor, "Удаление условия подсветки ЕВСК", obj)
    db.delete(obj)


@router.get("/evsk-candidates")
def evsk_candidates(
    actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    output = []
    for rule in db.scalars(select(EvskRule)):
        for result, comp in db.execute(
            select(CompetitionResult, Competition)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                Competition.discipline_id == rule.discipline_id,
                Competition.level == rule.level,
                Competition.state == "published",
                CompetitionResult.place <= rule.max_place,
            )
        ):
            count = len(
                db.scalars(
                    select(CompetitionResult.id).where(
                        CompetitionResult.competition_id == comp.id
                    )
                ).all()
            )
            if count >= rule.min_participants:
                output.append(
                    {
                        "athlete_id": result.athlete_id,
                        "full_name": db.get(Athlete, result.athlete_id).user.full_name,
                        "result_id": result.id,
                        "competition": comp.title,
                        "rank": rule.rank_name,
                        "source": rule.source,
                        "notice": "Предварительная подсказка; требуется проверка всех условий ЕВСК",
                    }
                )
    return output


@router.get("/notifications")
def notifications(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return [
        row(x)
        for x in db.scalars(
            select(Notification)
            .where(Notification.user_id == actor.user.id)
            .order_by(Notification.id.desc())
            .limit(200)
        )
        if visible_in_role(db, actor, x)
    ]


@router.patch("/notifications/{notification_id}/read")
def read_notice(
    notification_id: int,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    obj = require(db, Notification, notification_id)
    if obj.user_id != actor.user.id or not visible_in_role(db, actor, obj):
        raise HTTPException(403, "Нет доступа")
    obj.read_at = now()
    return row(obj)


@router.get("/audit")
def logs(actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    return [
        {
            **row(x),
            "full_name": db.get(User, x.user_id).full_name if x.user_id else "Система",
        }
        for x in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(500))
    ]


@router.get("/deadlines")
def list_deadlines(
    actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    today = date.today()
    ids = visible_athletes(db, actor)
    items = []
    for c in db.scalars(
        select(Competition).where(
            Competition.state == "open", Competition.deadline >= today
        )
    ):
        items.append(
            {"kind": "competition", "id": c.id, "title": c.title, "due_on": c.deadline}
        )
    for r in db.scalars(select(SportsRank).where(SportsRank.athlete_id.in_(ids))):
        items.append(
            {
                "kind": "rank",
                "id": r.id,
                "title": f"{db.get(Athlete, r.athlete_id).user.full_name}: {r.name}",
                "due_on": r.expires_on,
            }
        )
    if actor.role in ("judge", "admin"):
        query = select(JudgeCategory)
        if actor.role == "judge":
            query = query.where(JudgeCategory.judge_id == own(db, Judge, actor).id)
        for c in db.scalars(query):
            items.append(
                {
                    "kind": "category",
                    "id": c.id,
                    "title": f"{db.get(Judge, c.judge_id).user.full_name}: {c.name}",
                    "due_on": c.expires_on,
                }
            )
    if actor.role == "admin":
        items.extend(
            {"kind": "report", **row(d)}
            for d in db.scalars(select(Deadline).where(Deadline.done == False))
        )
        items.append(
            {
                "kind": "governor",
                "id": 0,
                "title": "Ходатайства на премии Губернатора",
                "due_on": date(
                    today.year if today.month == 1 else today.year + 1, 2, 1
                ),
            }
        )
    return sorted(items, key=lambda x: x["due_on"])


@router.post("/deadlines", status_code=201)
def add_deadline(
    data: DeadlineIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = Deadline(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Добавление срока отчёта", obj)
    return row(obj)


@router.patch("/deadlines/{deadline_id}")
def edit_deadline(
    deadline_id: int,
    data: DeadlineIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, Deadline, deadline_id)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    audit(db, actor, "Изменение срока отчёта", obj)
    return row(obj)
