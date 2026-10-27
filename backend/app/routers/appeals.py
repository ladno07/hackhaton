from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, select
from sqlalchemy.orm import Session
from typing import Literal
from app.db import get_db
from app.models import *
from app.schemas import AppealDecisionIn, AppealIn, ArchiveIn, ViolationIn
from app.security import Actor, allow
from app.services.appeals import *
from app.services.common import *
from app.services.documents import OfficialDocument
from app.services.notifications import admins, athlete_audience, notify
from app.routers.competitions import apply_correction, locked
from app.routers.reports import HEAD, download

router = APIRouter(tags=["Апелляции и нарушения"])

AppealStatus = Literal["pending", "upheld", "rejected", "withdrawn"]


def discipline_of(db, appeal):
    comp = db.get(Competition, appeal.competition_id) if appeal.competition_id else None
    return comp.discipline_id if comp else None


@router.get("/appeals")
def appeals(
    status: AppealStatus | None = None,
    actor: Actor = Depends(allow("admin", "ministry", "athlete", "coach", "judge")),
    db: Session = Depends(get_db),
):
    query = appeal_scope(db, actor, select(Appeal)).order_by(Appeal.id.desc())
    if status:
        query = query.where(Appeal.status == status)
    return [appeal_view(db, actor, a) for a in db.scalars(query)]


@router.get("/appeals/options")
def options(
    actor: Actor = Depends(allow("athlete", "coach")), db: Session = Depends(get_db)
):
    return appeal_options(db, actor)


@router.post("/appeals", status_code=201)
def submit(
    data: AppealIn,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    if data.subject == "result":
        result = require(db, CompetitionResult, data.result_id)
        comp = locked(db, result.competition_id)
        athlete = can_athlete(db, actor, result.athlete_id, comp.discipline_id)
        deadline = result_deadline(db, comp.id)
        if comp.state != "published" or not deadline:
            raise HTTPException(409, "Протокол ещё не опубликован")
        if deadline < date.today():
            raise HTTPException(
                409,
                f"Срок подачи апелляции истёк {deadline:%d.%m.%Y}: "
                f"{RESULT_APPEAL_DAYS} дня после публикации редакции протокола",
            )
        busy = Appeal.result_id == result.id
        fields = {
            "competition_id": comp.id,
            "result_id": result.id,
            "protocol_version": latest_version(db, comp.id).version,
        }
    else:
        violation = require(db, Violation, data.violation_id)
        athlete = can_athlete(db, actor, violation.athlete_id)
        if violation.status != "active":
            raise HTTPException(409, "Решение о нарушении уже отменено")
        if violation_deadline(violation) < date.today():
            raise HTTPException(
                409,
                f"Срок подачи апелляции истёк {violation_deadline(violation):%d.%m.%Y}",
            )
        busy = Appeal.violation_id == violation.id
        fields = {
            "competition_id": violation.competition_id,
            "violation_id": violation.id,
        }
    if db.scalar(select(Appeal.id).where(busy, Appeal.status == "pending")):
        raise HTTPException(409, "По этому решению уже есть апелляция на рассмотрении")
    obj = Appeal(
        athlete_id=athlete.id,
        subject=data.subject,
        reason=data.reason,
        request=data.request,
        submitted_by=actor.user.id,
        submitted_role=actor.role,
        **fields,
    )
    db.add(obj)
    audit(db, actor, "Подача апелляции", obj, {"subject": data.subject, **fields})
    notify(
        db,
        admins(db),
        "Новая апелляция",
        f"№ А-{obj.id}, {athlete.user.full_name}: {appeal_view(db, actor, obj)['subject_text']}",
        f"appeal:{obj.id}",
    )
    return appeal_view(db, actor, obj)


@router.post("/appeals/{appeal_id}/withdraw")
def withdraw(
    appeal_id: int,
    actor: Actor = Depends(allow("athlete", "coach")),
    db: Session = Depends(get_db),
):
    obj = require(db, Appeal, appeal_id)
    if not can_follow(db, actor, obj.athlete_id, discipline_of(db, obj)):
        raise HTTPException(404, "Апелляция не найдена")
    if obj.status != "pending":
        raise HTTPException(409, "Апелляция уже рассмотрена")
    obj.status = "withdrawn"
    obj.decided_at = now()
    audit(db, actor, "Отзыв апелляции", obj)
    return appeal_view(db, actor, obj)


@router.patch("/appeals/{appeal_id}")
def decide(
    appeal_id: int,
    data: AppealDecisionIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, Appeal, appeal_id)
    comp = locked(db, obj.competition_id) if obj.subject == "result" else None
    if obj.status != "pending":
        raise HTTPException(409, "Апелляция уже рассмотрена или отозвана")
    if data.correction and (data.status != "upheld" or obj.subject != "result"):
        raise HTTPException(
            422, "Протокол исправляется только по удовлетворённой апелляции на результат"
        )
    details = {"status": data.status, "decision": data.decision}
    if data.correction:
        if comp.state != "published":
            raise HTTPException(409, "Исправить можно только опубликованный протокол")
        fix = apply_correction(
            db, actor, comp, data.correction, f"Апелляция № А-{obj.id}: {data.decision}"
        )
        obj.resolution_version = fix["version"]
        details |= fix
    if data.status == "upheld" and obj.subject == "violation":
        violation = db.get(Violation, obj.violation_id)
        if violation.status == "active":
            cancel_violation(
                db, actor, violation, f"Апелляция № А-{obj.id} удовлетворена: {data.decision}"
            )
    obj.status = data.status
    obj.decision = data.decision
    obj.decided_by = actor.user.id
    obj.decided_at = now()
    audit(db, actor, "Рассмотрение апелляции", obj, details)
    view = appeal_view(db, actor, obj)
    notify(
        db,
        athlete_audience(db, obj.athlete_id, discipline_of(db, obj)),
        "Решение по апелляции",
        f"№ {view['number']}: {view['status_name'].lower()}. {data.decision}"
        + (
            f"\nОпубликована редакция протокола {obj.resolution_version}."
            if obj.resolution_version
            else ""
        ),
        f"appeal-decision:{obj.id}",
    )
    return {**view, "rank_warnings": details.get("rank_warnings", [])}


@router.get("/violations")
def violations(
    athlete_id: int | None = None,
    actor: Actor = Depends(allow("admin", "ministry", "athlete", "coach")),
    db: Session = Depends(get_db),
):
    query = select(Violation).order_by(Violation.occurred_on.desc(), Violation.id.desc())
    if actor.role not in ("admin", "ministry"):
        query = query.where(Violation.athlete_id.in_(visible_athletes(db, actor)))
    if athlete_id:
        query = query.where(Violation.athlete_id == athlete_id)
    return [violation_view(db, v) for v in db.scalars(query)]


@router.post("/violations", status_code=201)
def add_violation(
    data: ViolationIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    athlete = require(db, Athlete, data.athlete_id)
    if data.competition_id:
        comp = require(db, Competition, data.competition_id)
        if comp.state == "draft":
            raise HTTPException(422, "Соревнование ещё не опубликовано")
    obj = Violation(**data.model_dump(), created_by=actor.user.id)
    db.add(obj)
    if data.sanction == "suspension" and (
        not athlete.suspended_until or athlete.suspended_until < data.suspended_until
    ):
        athlete.suspended_until = data.suspended_until
        athlete.suspension_reason = data.description
    audit(db, actor, "Фиксация нарушения", obj, data.model_dump(mode="json"))
    notify(
        db,
        athlete_audience(db, athlete.id),
        "Зафиксировано нарушение",
        f"{violation_text(obj)}. {data.description}\n"
        f"Апелляцию можно подать до {violation_deadline(obj):%d.%m.%Y}.",
        f"violation:{obj.id}",
    )
    return violation_view(db, obj)


def cancel_violation(db, actor, obj, reason):
    obj.status = "cancelled"
    obj.cancel_reason = reason
    obj.cancelled_at = now()
    if obj.sanction == "suspension":
        restore_suspension(db, db.get(Athlete, obj.athlete_id), obj)
    audit(db, actor, "Отмена нарушения", obj, {"reason": reason})
    notify(
        db,
        athlete_audience(db, obj.athlete_id),
        "Решение о нарушении отменено",
        f"{violation_text(obj)}. {reason}",
        f"violation-cancel:{obj.id}",
    )


@router.post("/violations/{violation_id}/cancel")
def cancel(
    violation_id: int,
    data: ArchiveIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, Violation, violation_id)
    if obj.status != "active":
        raise HTTPException(409, "Решение уже отменено")
    cancel_violation(db, actor, obj, data.reason)
    return violation_view(db, obj)


@router.get("/exports/appeals.{fmt}")
def export_appeals(
    fmt: str,
    year: int | None = Query(None, ge=2000, le=2100, description="По умолчанию текущий"),
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    year = year or date.today().year
    items = [
        appeal_view(db, actor, a)
        for a in db.scalars(
            select(Appeal)
            .where(extract("year", Appeal.created_at) == year)
            .order_by(Appeal.id)
        )
    ]
    counts = {s: sum(i["status"] == s for i in items) for s in STATUSES}
    return download(
        OfficialDocument(
            kind="Журнал",
            title=f"апелляций за {year} год",
            headers=["№", "Дата", "Спортсмен", "Предмет", "Доводы", "Статус", "Решение"],
            rows=[
                [
                    i["number"],
                    f"{i['created_at']:%d.%m.%Y}",
                    i["full_name"],
                    i["subject_text"],
                    i["reason"],
                    i["status_name"]
                    + (
                        f", редакция протокола {i['resolution_version']}"
                        if i["resolution_version"]
                        else ""
                    ),
                    i["decision"] or "—",
                ]
                for i in items
            ],
            dated=date.today(),
            meta=[
                ("Всего апелляций", len(items)),
                *[(STATUSES[s], counts[s]) for s in STATUSES if counts[s]],
            ],
            signatures=[HEAD, ("Исполнитель", actor.user.full_name)],
        ),
        fmt,
        f"appeals-{year}",
    )
