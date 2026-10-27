from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import AwardRuleIn, AwardStatusIn, Level
from app.security import Actor, allow
from app.services.awards import award_list, current_year
from app.services.common import *
from app.services.documents import OfficialDocument
from app.services.notifications import notify
from app.routers.reports import HEAD, download

router = APIRouter(tags=["Премии Губернатора"])

LEVELS = {
    "regional": "региональный",
    "interregional": "межрегиональный",
    "russian_championship": "чемпионат России",
    "russian_junior": "первенство России",
}
STATUS_NAMES = {
    "candidate": "Претендент",
    "nominated": "Включён в ходатайство",
    "awarded": "Премия присуждена",
    "rejected": "Отказано",
}
# from -> allowed targets; the same status only updates comment and order
TRANSITIONS = {
    "candidate": {"nominated", "rejected"},
    "nominated": {"nominated", "awarded", "rejected", "candidate"},
    "rejected": {"rejected", "nominated", "candidate"},
    "awarded": {"awarded", "nominated"},
}
Year = Query(
    None,
    ge=2000,
    le=2100,
    description="Год достижений; по умолчанию тот, ходатайства за который подаются до ближайшего 1 февраля",
)


def checked(year):
    year = year or current_year()
    if year > date.today().year:
        raise HTTPException(422, "Достижения будущего года ещё не известны")
    return year


def basis_text(basis):
    if not basis:
        return "—"
    team = f", команда «{basis['team_name']}»" if basis.get("team_name") else ""
    return (
        f"{basis['place']} место{team} — {basis['title']} "
        f"({LEVELS.get(basis['level'], basis['level'])}, "
        f"{date.fromisoformat(basis['date']):%d.%m.%Y})"
    )


def rubles(n):
    return f"{n:,}".replace(",", " ") + " ₽"


@router.get("/governor-award-rules")
def award_rules(
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    return [row(r) for r in db.scalars(select(GovernorAwardRule))]


@router.put("/governor-award-rules/{level}")
def edit_award_rule(
    level: Level,
    data: AwardRuleIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, GovernorAwardRule, level)
    before = row(obj)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    audit(
        db,
        actor,
        "Изменение сумм премий Губернатора",
        obj,
        {"level": level, "before": before, "after": data.model_dump()},
    )
    return row(obj)


@router.get("/governor-awards")
def governor_awards(
    year: int | None = Year,
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    return award_list(db, checked(year))


@router.put("/governor-awards/{year}/{athlete_id}")
def set_award_status(
    year: int,
    athlete_id: int,
    data: AwardStatusIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    checked(year)
    item = next(
        (i for i in award_list(db, year)["items"] if i["athlete_id"] == athlete_id),
        None,
    )
    if item is None:
        raise HTTPException(404, "Спортсмен не является претендентом на премию за этот год")
    if data.status not in TRANSITIONS[item["status"]]:
        raise HTTPException(
            409,
            f"Нельзя перевести из статуса «{STATUS_NAMES[item['status']]}» "
            f"в «{STATUS_NAMES[data.status]}»",
        )
    entering = data.status != item["status"]
    # put forward again: amount and basis are taken from the current protocols
    forward = data.status == "nominated" and item["status"] in ("candidate", "rejected")
    if forward and not item["eligible"]:
        raise HTTPException(
            409,
            "Спортсмен отстранён"
            if item["suspended"]
            else "Достижение больше не подтверждается протоколами",
        )
    if data.status == "awarded" and not data.order_number:
        raise HTTPException(422, "Укажите номер распоряжения о присуждении премии")
    if data.status == "rejected" and not data.comment:
        raise HTTPException(422, "Укажите причину отказа")
    if item["status"] == "awarded" and data.status == "nominated" and not data.comment:
        raise HTTPException(422, "Укажите причину отмены присуждения")

    obj = db.scalar(
        select(GovernorAward).where(
            GovernorAward.year == year, GovernorAward.athlete_id == athlete_id
        )
    )
    details = {"year": year, "athlete_id": athlete_id, "from": item["status"], "to": data.status}
    if data.status == "candidate":
        audit(db, actor, "Возврат в претенденты на премию Губернатора", obj, details)
        db.delete(obj)
        db.flush()
        return {**item, "status": "candidate", "comment": "", "order_number": None}
    if obj is None or forward:
        obj = obj or GovernorAward(year=year, athlete_id=athlete_id)
        db.add(obj)
        best = item["achievements"][0] if item["achievements"] else item["basis"]
        obj.basis = best
        obj.amount = best["amount"]
    obj.status = data.status
    obj.comment = data.comment
    obj.order_number = data.order_number if data.status == "awarded" else None
    obj.updated_by = actor.user.id
    obj.updated_at = now()
    audit(
        db,
        actor,
        "Изменение статуса премии Губернатора",
        obj,
        {**details, "amount": obj.amount, "order_number": obj.order_number},
    )
    if data.status == "awarded" and entering:
        athlete = db.get(Athlete, athlete_id)
        notify(
            db,
            [athlete.user_id],
            "Премия Губернатора",
            f"Вам присуждена премия Губернатора за {year} год: {basis_text(obj.basis)}. "
            f"Распоряжение № {obj.order_number}.",
            f"governor-award:{obj.id}:awarded",
        )
    return next(i for i in award_list(db, year)["items"] if i["athlete_id"] == athlete_id)


@router.get("/exports/governor-awards.{fmt}")
def export_governor_awards(
    fmt: str,
    year: int | None = Year,
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    year = checked(year)
    data = award_list(db, year)
    chosen = [i for i in data["items"] if i["status"] in ("nominated", "awarded")]
    rows = [
        [
            n,
            i["full_name"],
            i["organization"] or i["municipality"],
            basis_text(i["basis"]),
            rubles(i["amount"]),
            STATUS_NAMES[i["status"]]
            + (f", распоряжение № {i['order_number']}" if i["order_number"] else ""),
        ]
        for n, i in enumerate(chosen, 1)
    ]
    return download(
        OfficialDocument(
            kind="Ходатайство",
            title="о присуждении премий Губернатора Оренбургской области "
            "спортсменам по спортивному программированию",
            headers=["№", "Спортсмен", "Организация", "Достижение", "Сумма", "Статус"],
            rows=rows,
            dated=date.today(),
            number="",
            meta=[
                ("Год достижений", f"{year}"),
                ("Срок подачи", f"{data['deadline']:%d.%m.%Y}"),
            ],
            intro=[
                "Федерация ходатайствует о присуждении премий спортсменам, "
                f"показавшим высокие результаты в {year} году. Достижения "
                "подтверждены опубликованными итоговыми протоколами."
            ],
            outro=[
                f"Количество спортсменов: {len(chosen)}. "
                f"Общая сумма: {rubles(data['totals']['nominated_amount'])}."
            ],
            signatures=[HEAD, ("Исполнитель", actor.user.full_name)],
        ),
        fmt,
        "governor-awards",
    )
