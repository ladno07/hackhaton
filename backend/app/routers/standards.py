from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Literal
from app.db import get_db
from app.models import *
from app.schemas import Sex, Stage, StageTransferIn, StandardIn, StandardResultIn
from app.security import Actor, allow
from app.services.common import *
from app.services.documents import OfficialDocument
from app.services.notifications import admins, athlete_audience, notify
from app.services.standards import *
from app.routers.reports import HEAD, download

router = APIRouter(tags=["Нормативы и аттестация"])
READERS = ("admin", "ministry", "athlete", "coach")


def visible(db, actor, athlete_id):
    if athlete_id not in visible_athletes(db, actor):
        raise HTTPException(404, "Спортсмен не найден")
    return require(db, Athlete, athlete_id)


@router.get("/standards/meta")
def meta(actor: Actor = Depends(allow(*READERS))):
    return {
        "stages": [
            {"code": k, "name": v, "short": SHORT[k], "rank": STAGE_RANKS.get(k)}
            for k, v in STAGES.items()
        ],
        "categories": CATEGORIES,
        "valid_days": VALID_DAYS,
    }


@router.get("/standards")
def standards(
    stage: Stage | None = None,
    category: Literal["ofp", "sfp"] | None = None,
    sex: Sex | None = None,
    discipline_id: int | None = None,
    archived: bool = False,
    actor: Actor = Depends(allow(*READERS)),
    db: Session = Depends(get_db),
):
    query = select(TrainingStandard).order_by(
        TrainingStandard.stage,
        TrainingStandard.category,
        TrainingStandard.sort_order,
        TrainingStandard.id,
    )
    query = query.where(
        TrainingStandard.archived_at.is_not(None)
        if archived
        else TrainingStandard.archived_at.is_(None)
    )
    if stage:
        query = query.where(TrainingStandard.stage == stage)
    if category:
        query = query.where(TrainingStandard.category == category)
    if sex:
        query = query.where(
            (TrainingStandard.sex == sex) | TrainingStandard.sex.is_(None)
        )
    if discipline_id:
        query = query.where(
            (TrainingStandard.discipline_id == discipline_id)
            | TrainingStandard.discipline_id.is_(None)
        )
    order = list(STAGES)
    items = [standard_view(db, s) for s in db.scalars(query)]
    return sorted(items, key=lambda s: order.index(s["stage"]))


def check_discipline(db, data):
    if data.discipline_id:
        require(db, Discipline, data.discipline_id)


@router.post("/standards", status_code=201)
def add_standard(
    data: StandardIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    check_discipline(db, data)
    obj = TrainingStandard(**data.model_dump())
    db.add(obj)
    audit(db, actor, "Добавление норматива", obj, data.model_dump())
    return standard_view(db, obj)


@router.put("/standards/{standard_id}")
def edit_standard(
    standard_id: int,
    data: StandardIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, TrainingStandard, standard_id)
    check_discipline(db, data)
    used = db.scalar(
        select(StandardResult.id).where(StandardResult.standard_id == obj.id)
    )
    # results keep their meaning: what was measured and on which stage
    if used and (
        obj.stage,
        obj.category,
        obj.better,
        obj.unit,
    ) != (data.stage, data.category, data.better, data.unit):
        raise HTTPException(
            409,
            "По нормативу уже есть результаты: этап, вид, единица и направление "
            "не меняются. Отправьте норматив в архив и добавьте новый",
        )
    before = {"threshold": obj.threshold}
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    audit(db, actor, "Изменение норматива", obj, {**data.model_dump(), "before": before})
    return standard_view(db, obj)


@router.post("/standards/{standard_id}/archive")
def archive_standard(
    standard_id: int,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, TrainingStandard, standard_id)
    obj.archived_at = obj.archived_at or now()
    audit(db, actor, "Архивирование норматива", obj)
    return standard_view(db, obj)


@router.post("/standards/{standard_id}/restore")
def restore_standard(
    standard_id: int,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, TrainingStandard, standard_id)
    obj.archived_at = None
    audit(db, actor, "Восстановление норматива", obj)
    return standard_view(db, obj)


def summary(state):
    return {k: v for k, v in state.items() if k != "items"}


@router.get("/attestation")
def attestation(
    ready: bool | None = None,
    actor: Actor = Depends(allow(*READERS)),
    db: Session = Depends(get_db),
):
    ids = visible_athletes(db, actor)
    items = [
        summary(readiness(db, a))
        for a in db.scalars(select(Athlete).where(Athlete.id.in_(ids)).order_by(Athlete.id))
    ]
    if ready is not None:
        items = [i for i in items if i["ready"] == ready]
    # ready first, then by progress
    return sorted(
        items,
        key=lambda i: (not i["ready"], -(i["passed"] / i["total"] if i["total"] else 0)),
    )


@router.get("/attestation/history")
def history(
    actor: Actor = Depends(allow(*READERS)),
    db: Session = Depends(get_db),
):
    ids = visible_athletes(db, actor)
    results = db.scalars(
        select(StandardResult)
        .where(StandardResult.athlete_id.in_(ids))
        .order_by(StandardResult.tested_on.desc(), StandardResult.id.desc())
        .limit(300)
    )
    transfers = db.scalars(
        select(StageTransfer)
        .where(StageTransfer.athlete_id.in_(ids))
        .order_by(StageTransfer.decided_on.desc(), StageTransfer.id.desc())
    )
    return {
        "results": [result_view(db, r) for r in results],
        "transfers": [transfer_view(db, t) for t in transfers],
    }


@router.get("/attestation/{athlete_id}")
def athlete_attestation(
    athlete_id: int,
    actor: Actor = Depends(allow(*READERS)),
    db: Session = Depends(get_db),
):
    athlete = visible(db, actor, athlete_id)
    state = readiness(db, athlete)
    stage = state["stage"]
    # what may be recorded: standards of the next stage and of the current one
    recordable = {
        s.id: standard_view(db, s)
        for code in filter(None, [state["target"], stage])
        for s in applicable(db, athlete, code)
    }
    return {
        **state,
        "recordable": list(recordable.values()),
        "can_record": actor.role in ("admin", "coach"),
        "can_transfer": actor.role == "admin" and state["ready"],
        "results": [
            result_view(db, r)
            for r in db.scalars(
                select(StandardResult)
                .where(StandardResult.athlete_id == athlete.id)
                .order_by(StandardResult.tested_on.desc(), StandardResult.id.desc())
            )
        ],
        "transfers": [
            transfer_view(db, t)
            for t in db.scalars(
                select(StageTransfer)
                .where(StageTransfer.athlete_id == athlete.id)
                .order_by(StageTransfer.decided_on.desc(), StageTransfer.id.desc())
            )
        ],
    }


def announce_ready(db, athlete):
    state = readiness(db, athlete)
    if not state["ready"]:
        return
    name = athlete.user.full_name
    notify(
        db,
        [*admins(db), *athlete_audience(db, athlete.id)],
        "Готов к переводу на следующий этап",
        f"{name}: выполнены нормативы этапа «{state['target_name']}»"
        + (f", разряд «{state['rank']}»" if state["rank_required"] else "")
        + ". Перевод оформляет федерация.",
        f"stage-ready:{athlete.id}:{state['target']}",
    )


@router.post("/attestation/{athlete_id}/results", status_code=201)
def add_result(
    athlete_id: int,
    data: StandardResultIn,
    actor: Actor = Depends(allow("admin", "coach")),
    db: Session = Depends(get_db),
):
    standard = require(db, TrainingStandard, data.standard_id)
    athlete = can_athlete(db, actor, athlete_id, standard.discipline_id)
    if standard.archived_at:
        raise HTTPException(409, "Норматив в архиве")
    if standard not in applicable(db, athlete, standard.stage):
        raise HTTPException(
            422,
            "Норматив не относится к спортсмену: другой пол или дисциплина"
            + (" (пол не указан в профиле)" if not athlete.user.sex and standard.sex else ""),
        )
    if data.tested_on < athlete.user.birth_date:
        raise HTTPException(422, "Дата сдачи раньше даты рождения")
    obj = StandardResult(
        athlete_id=athlete.id,
        standard_id=standard.id,
        value=data.value,
        tested_on=data.tested_on,
        threshold=standard.threshold,
        passed=meets(standard, data.value),
        comment=data.comment,
        recorded_by=actor.user.id,
        recorded_role=actor.role,
    )
    db.add(obj)
    audit(
        db,
        actor,
        "Результат норматива",
        obj,
        {**data.model_dump(mode="json"), "threshold": obj.threshold, "passed": obj.passed},
    )
    announce_ready(db, athlete)
    return result_view(db, obj)


@router.delete("/attestation/results/{result_id}", status_code=204)
def delete_result(
    result_id: int,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, StandardResult, result_id)
    view = result_view(db, obj)
    audit(
        db,
        actor,
        "Удаление результата норматива",
        obj,
        {
            "athlete_id": obj.athlete_id,
            "standard": view["standard"],
            "value": obj.value,
            "tested_on": obj.tested_on.isoformat(),
        },
    )
    db.delete(obj)


@router.post("/attestation/{athlete_id}/transfer", status_code=201)
def transfer_stage(
    athlete_id: int,
    data: StageTransferIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    athlete = require(db, Athlete, athlete_id)
    state = readiness(db, athlete)
    if data.to_stage != state["target"]:
        raise HTTPException(
            409,
            f"Перевод возможен только на следующий этап: «{state['target_name']}»"
            if state["target"]
            else "Спортсмен на последнем этапе подготовки",
        )
    if not state["ready"]:
        raise HTTPException(409, "Спортсмен не готов к переводу: " + "; ".join(state["blockers"]))
    obj = StageTransfer(
        athlete_id=athlete.id,
        from_stage=athlete.training_stage,
        to_stage=data.to_stage,
        decided_on=data.decided_on,
        order_number=data.order_number,
        comment=data.comment,
        basis=basis_of(state),
        created_by=actor.user.id,
    )
    db.add(obj)
    athlete.training_stage = STAGES[data.to_stage]
    audit(db, actor, "Перевод на этап подготовки", obj, data.model_dump(mode="json"))
    notify(
        db,
        athlete_audience(db, athlete.id),
        "Перевод на этап подготовки",
        f"{athlete.user.full_name}: {'переведён' if obj.from_stage else 'зачислен'} "
        f"на {STAGES[data.to_stage].lower()}, приказ № {data.order_number} "
        f"от {data.decided_on:%d.%m.%Y}.",
        f"stage-transfer:{obj.id}",
    )
    return transfer_view(db, obj)


@router.get("/exports/attestation.{fmt}")
def export_attestation(
    fmt: str,
    stage: Stage | None = Query(None, description="Этап, на который переводят"),
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    items = [readiness(db, a) for a in db.scalars(select(Athlete).order_by(Athlete.id))]
    if stage:
        items = [i for i in items if i["target"] == stage]
    items = [i for i in items if i["target"]]
    ready = [i for i in items if i["ready"]]
    title = "готовности спортсменов к переводу на следующий этап подготовки"
    return download(
        OfficialDocument(
            kind="Ведомость",
            title=title + (f" ({STAGES[stage].lower()})" if stage else ""),
            headers=["Спортсмен", "Текущий этап", "Следующий этап", "Нормативы", "Разряд", "Итог"],
            rows=[
                [
                    i["full_name"],
                    i["training_stage"] or "Не указан",
                    i["target_name"],
                    f"{i['passed']} из {i['total']}",
                    (i["rank"] or "—")
                    + (f" (нужен {i['rank_required']})" if i["rank_required"] else ""),
                    "Готов к переводу" if i["ready"] else "; ".join(i["blockers"]),
                ]
                for i in items
            ],
            intro=[
                "Сравнение лучших результатов сдачи нормативов ОФП и СФП за последние "
                f"{VALID_DAYS} дней с действующими порогами справочника по этапу, "
                "дисциплине и полу спортсмена; для этапов ССМ и ВСМ учитывается разряд."
            ],
            dated=date.today(),
            meta=[("Всего спортсменов", len(items)), ("Готовы к переводу", len(ready))],
            signatures=[HEAD, ("Исполнитель", actor.user.full_name)],
        ),
        fmt,
        "attestation",
    )
