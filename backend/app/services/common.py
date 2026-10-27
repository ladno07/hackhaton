from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.inspection import inspect
from app.models import *


def row(obj):
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def require(db, model, key):
    obj = db.get(model, key)
    if obj is None:
        raise HTTPException(404, "Запись не найдена")
    return obj


def age_at(born, at=None):
    at = at or date.today()
    return at.year - born.year - ((at.month, at.day) < (born.month, born.day))


def audit(db, actor, action, obj, details=None):
    db.flush()
    db.add(
        AuditLog(
            user_id=actor.user.id,
            active_role=actor.role,
            action=action,
            entity=obj.__tablename__,
            entity_id=str(getattr(obj, "id", "")),
            details=details or {},
        )
    )


def own(db, model, actor):
    obj = db.scalar(select(model).where(model.user_id == actor.user.id))
    if not obj:
        raise HTTPException(403, "Профиль роли не найден")
    return obj


def can_athlete(db, actor, athlete_id, discipline_id=None):
    athlete = require(db, Athlete, athlete_id)
    if actor.role == "admin":
        return athlete
    if actor.role == "athlete" and athlete.user_id == actor.user.id:
        return athlete
    if actor.role == "coach":
        coach = own(db, Coach, actor)
        query = select(AthleteCoach).where(
            AthleteCoach.athlete_id == athlete_id,
            AthleteCoach.coach_id == coach.id,
            AthleteCoach.status == "active",
        )
        if discipline_id:
            query = query.where(AthleteCoach.discipline_id == discipline_id)
        if db.scalar(query):
            return athlete
    raise HTTPException(403, "Спортсмен не относится к активному кабинету")


def visible_athletes(db, actor):
    if actor.role in ("admin", "ministry"):
        return set(db.scalars(select(Athlete.id)).all())
    if actor.role == "athlete":
        return {own(db, Athlete, actor).id}
    if actor.role == "coach":
        coach = own(db, Coach, actor)
        return set(
            db.scalars(
                select(AthleteCoach.athlete_id).where(
                    AthleteCoach.coach_id == coach.id, AthleteCoach.status == "active"
                )
            ).all()
        )
    return set()


def active_card(db, model, actor):
    card = own(db, model, actor)
    if card.archived_at:
        raise HTTPException(409, "Карточка в архиве — действие недоступно")
    return card


def memberships(db, athlete_id):
    return db.scalars(
        select(AthleteOrganization)
        .where(AthleteOrganization.athlete_id == athlete_id)
        .order_by(AthleteOrganization.start_date, AthleteOrganization.id)
    ).all()


def transfer(db, athlete, organization_id, on=None):
    """Move the athlete to another organization (or none) starting from `on`."""
    on = on or date.today()
    if on > date.today():
        raise HTTPException(422, "Дата перехода не может быть в будущем")
    periods = memberships(db, athlete.id)
    current = next((p for p in periods if p.end_date is None), None)
    if (current.organization_id if current else None) == organization_id:
        athlete.organization_id = organization_id
        return
    # Only the open period may be cut; closed ones must end before the transfer.
    if any(
        p.start_date > on or p is not current and p.end_date >= on for p in periods
    ):
        raise HTTPException(422, "Дата перехода пересекается с историей организаций")
    if current:
        if current.start_date == on:
            db.delete(current)
        else:
            current.end_date = on - timedelta(days=1)
    if organization_id:
        db.add(
            AthleteOrganization(
                athlete_id=athlete.id, organization_id=organization_id, start_date=on
            )
        )
    athlete.organization_id = organization_id
    db.flush()
