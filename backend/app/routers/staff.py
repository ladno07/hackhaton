from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import ArchiveIn, StaffCardIn, StaffCreate
from app.security import Actor, current_actor, allow, password_hash
from app.services.common import *
from app.services.notifications import notify

router = APIRouter(tags=["Тренеры и судьи"])

# role -> card model, disciplines model, its foreign key, genitive for messages
KINDS = {
    "coach": (Coach, CoachDiscipline, "coach_id", "тренера"),
    "judge": (Judge, JudgeDiscipline, "judge_id", "судьи"),
}
PRIVATE = ["phone", "contact_email", "birth_date", "sex", "email"]
CARD_FIELDS = [
    "organization_id",
    "municipality",
    "phone",
    "contact_email",
    "qualification",
    "experience_since",
    "about",
]


def staff_view(db, kind, card, actor):
    _, disciplines, fk, _ = KINDS[kind]
    org = db.get(Organization, card.organization_id) if card.organization_id else None
    item = {
        **row(card),
        "full_name": card.user.full_name,
        "sex": card.user.sex,
        "birth_date": card.user.birth_date,
        "email": card.user.email,
        "organization": org.name if org else "Без организации",
        "discipline_ids": list(
            db.scalars(
                select(disciplines.discipline_id).where(
                    getattr(disciplines, fk) == card.id
                )
            )
        ),
    }
    if kind == "judge":
        item["categories"] = [
            row(c)
            for c in db.scalars(
                select(JudgeCategory)
                .where(JudgeCategory.judge_id == card.id)
                .order_by(JudgeCategory.assigned_on.desc())
            )
        ]
    if actor.role != "admin" and card.user_id != actor.user.id:
        for key in PRIVATE:
            item.pop(key)
    return item


def staff_list(db, kind, actor, archived):
    model = KINDS[kind][0]
    if archived and actor.role != "admin":
        raise HTTPException(403, "Архив доступен администратору")
    query = select(model).where(
        model.archived_at.is_not(None) if archived else model.archived_at.is_(None)
    )
    cards = db.scalars(query.order_by(model.id)).all()
    return [staff_view(db, kind, c, actor) for c in cards]


def staff_detail(db, kind, card_id, actor):
    card = require(db, KINDS[kind][0], card_id)
    if card.archived_at and actor.role != "admin" and card.user_id != actor.user.id:
        raise HTTPException(404, "Запись не найдена")
    return staff_view(db, kind, card, actor)


def fill(db, kind, card, data: StaffCardIn):
    _, disciplines, fk, _ = KINDS[kind]
    if data.organization_id:
        require(db, Organization, data.organization_id)
    for discipline_id in data.discipline_ids:
        require(db, Discipline, discipline_id)
    card.user.full_name = data.full_name
    card.user.sex = data.sex
    card.user.birth_date = data.birth_date
    values = data.model_dump(mode="json", include=set(CARD_FIELDS))
    for key in CARD_FIELDS:
        setattr(card, key, values[key])
    db.flush()
    db.execute(delete(disciplines).where(getattr(disciplines, fk) == card.id))
    db.add_all(
        [
            disciplines(**{fk: card.id, "discipline_id": d})
            for d in data.discipline_ids
        ]
    )


def staff_create(db, kind, data: StaffCreate, actor):
    model, _, _, genitive = KINDS[kind]
    email = str(data.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        if not data.password:
            raise HTTPException(422, "Для новой учётной записи задайте пароль")
        user = User(
            email=email,
            full_name=data.full_name,
            birth_date=data.birth_date,
            password_hash=password_hash.hash(data.password),
        )
        db.add(user)
        db.flush()
    elif data.password:
        raise HTTPException(
            409, "Пользователь с этим email уже есть — пароль не меняется"
        )
    existing = db.scalar(select(model).where(model.user_id == user.id))
    if existing:
        raise HTTPException(
            409,
            f"Карточка {genitive} в архиве — восстановите её"
            if existing.archived_at
            else f"Карточка {genitive} уже есть",
        )
    if kind not in [r.id for r in user.roles]:
        user.roles.append(require(db, Role, kind))
    card = model(user_id=user.id)
    card.user = user
    db.add(card)
    fill(db, kind, card, data)
    audit(db, actor, f"Создание карточки {genitive}", card)
    notify(
        db,
        [user.id],
        f"Создана карточка {genitive}",
        "Кабинет доступен после входа с выбранной ролью",
        f"staff:{kind}:{card.id}",
    )
    return staff_view(db, kind, card, actor)


def staff_update(db, kind, card_id, data: StaffCardIn, actor):
    model, _, _, genitive = KINDS[kind]
    card = require(db, model, card_id)
    if actor.role != "admin":
        if card.user_id != actor.user.id:
            raise HTTPException(403, "Можно изменить только свою карточку")
        if card.archived_at:
            raise HTTPException(409, "Карточка в архиве")
    fill(db, kind, card, data)
    audit(db, actor, f"Изменение карточки {genitive}", card)
    return staff_view(db, kind, card, actor)


def staff_archive(db, kind, card_id, data: ArchiveIn, actor):
    model, _, _, genitive = KINDS[kind]
    card = require(db, model, card_id)
    if card.archived_at:
        raise HTTPException(409, "Карточка уже в архиве")
    card.archived_at = now()
    card.archive_reason = data.reason
    if kind == "coach":
        links = db.scalars(
            select(AthleteCoach).where(
                AthleteCoach.coach_id == card.id,
                AthleteCoach.status.in_(["active", "pending"]),
            )
        ).all()
        for link in links:
            # pending -> paused is not a valid transition, unconfirmed requests end
            link.status = "paused" if link.status == "active" else "ended"
            db.add(
                LinkHistory(link_id=link.id, actor_id=actor.user.id, status=link.status)
            )
            notify(
                db,
                [db.get(Athlete, link.athlete_id).user_id],
                "Связь с тренером изменена",
                f"{card.user.full_name}: тренер в архиве, связь — {link.status}",
                f"link-archive:{link.id}:{card.archived_at.isoformat()}",
            )
    audit(db, actor, f"Архивация карточки {genitive}", card, data.model_dump())
    notify(
        db,
        [card.user_id],
        f"Карточка {genitive} перенесена в архив",
        data.reason,
        f"staff-archive:{kind}:{card.id}:{card.archived_at.isoformat()}",
    )
    return staff_view(db, kind, card, actor)


def staff_restore(db, kind, card_id, actor):
    model, _, _, genitive = KINDS[kind]
    card = require(db, model, card_id)
    if not card.archived_at:
        raise HTTPException(409, "Карточка не в архиве")
    card.archived_at = None
    card.archive_reason = None
    audit(db, actor, f"Восстановление карточки {genitive}", card)
    notify(
        db,
        [card.user_id],
        f"Карточка {genitive} восстановлена",
        "Кабинет снова доступен полностью",
        f"staff-restore:{kind}:{card.id}:{now().isoformat()}",
    )
    return staff_view(db, kind, card, actor)


@router.get("/coaches")
def coaches(
    archived: bool = False,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    return staff_list(db, "coach", actor, archived)


@router.get("/coaches/{card_id}")
def coach_detail(
    card_id: int, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    return staff_detail(db, "coach", card_id, actor)


@router.post("/coaches", status_code=201)
def create_coach(
    data: StaffCreate,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    return staff_create(db, "coach", data, actor)


@router.put("/coaches/{card_id}")
def update_coach(
    card_id: int,
    data: StaffCardIn,
    actor: Actor = Depends(allow("admin", "coach")),
    db: Session = Depends(get_db),
):
    return staff_update(db, "coach", card_id, data, actor)


@router.post("/coaches/{card_id}/archive")
def archive_coach(
    card_id: int,
    data: ArchiveIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    return staff_archive(db, "coach", card_id, data, actor)


@router.post("/coaches/{card_id}/restore")
def restore_coach(
    card_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    return staff_restore(db, "coach", card_id, actor)


@router.get("/judges")
def judges(
    archived: bool = False,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    return staff_list(db, "judge", actor, archived)


@router.get("/judges/{card_id}")
def judge_detail(
    card_id: int, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)
):
    return staff_detail(db, "judge", card_id, actor)


@router.post("/judges", status_code=201)
def create_judge(
    data: StaffCreate,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    return staff_create(db, "judge", data, actor)


@router.put("/judges/{card_id}")
def update_judge(
    card_id: int,
    data: StaffCardIn,
    actor: Actor = Depends(allow("admin", "judge")),
    db: Session = Depends(get_db),
):
    return staff_update(db, "judge", card_id, data, actor)


@router.post("/judges/{card_id}/archive")
def archive_judge(
    card_id: int,
    data: ArchiveIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    return staff_archive(db, "judge", card_id, data, actor)


@router.post("/judges/{card_id}/restore")
def restore_judge(
    card_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    return staff_restore(db, "judge", card_id, actor)
