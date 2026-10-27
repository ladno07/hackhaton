from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import Login, Register
from app.security import Actor, current_actor, password_hash, token
from app.services.common import audit
from app.services.athlete_ids import public_athlete_id

from app.services.login_sessions import (
    session_origin,
    create_session,
    forget_session,
    session_user,
)

router = APIRouter(
    prefix="/auth", tags=["Авторизация"], dependencies=[Depends(session_origin)]
)
DUMMY_HASH = password_hash.hash("dummy-password-not-a-user")


def user_view(db, user):
    profiles = {
        name: db.scalar(select(model.id).where(model.user_id == user.id))
        for name, model in [
            ("athlete_id", Athlete),
            ("coach_id", Coach),
            ("judge_id", Judge),
        ]
    }
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "birth_date": user.birth_date,
        "sex": user.sex,
        "roles": [r.id for r in user.roles],
        "consent_at": user.consent_at,
        "consent_version": user.consent_version,
        "guardian_name": user.guardian_name,
        "guardian_consent_at": user.guardian_consent_at,
        **profiles,
        "athlete_public_id": public_athlete_id(profiles["athlete_id"])
        if profiles["athlete_id"]
        else None,
    }


@router.post("/register", status_code=201)
def register(
    data: Register, request: Request, response: Response, db: Session = Depends(get_db)
):
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Этот email уже зарегистрирован")
    user = User(
        email=email,
        full_name=data.full_name,
        birth_date=data.birth_date,
        sex=data.sex,
        password_hash=password_hash.hash(data.password),
        guardian_name=data.guardian_name,
        guardian_consent_at=now() if data.guardian_consent else None,
    )
    role = db.get(Role, data.role)
    if not role:
        raise HTTPException(503, "Справочники не инициализированы")
    user.roles.append(role)
    db.add(user)
    db.flush()
    model = {"athlete": Athlete, "coach": Coach, "judge": Judge}[data.role]
    db.add(model(user_id=user.id))
    audit(
        db,
        Actor(user, data.role),
        "Регистрация и согласие ПД",
        user,
        {"consent_version": user.consent_version},
    )
    session_id = create_session(db, user, request, response)
    return {
        "access_token": token(user, session_id),
        "token_type": "bearer",
        "user": user_view(db, user),
    }


@router.post("/login")
def login(
    data: Login, request: Request, response: Response, db: Session = Depends(get_db)
):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = password_hash.verify(
        data.password, user.password_hash if user else DUMMY_HASH
    )
    if not user or not valid:
        raise HTTPException(401, "Неверный email или пароль")
    audit(db, Actor(user, user.roles[0].id), "Вход в систему", user)
    session_id = create_session(db, user, request, response)
    return {
        "access_token": token(user, session_id),
        "token_type": "bearer",
        "user": user_view(db, user),
    }


@router.get("/me")
def me(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return user_view(db, actor.user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    user, session_id = session_user(db, request)
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": token(user, session_id),
        "token_type": "bearer",
        "user": user_view(db, user),
    }


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    forget_session(db, request, response)
