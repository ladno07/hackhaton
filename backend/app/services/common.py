from datetime import date
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
    if actor.role == "admin":
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
