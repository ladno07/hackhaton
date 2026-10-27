from datetime import timedelta, timezone
from hashlib import sha256
import secrets
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete
from app.config import settings
from app.models import LoginSession, now

COOKIE = "orencode_session"
MAX_AGE = 30 * 24 * 60 * 60


def session_origin(request: Request):
    allowed = {
        settings.public_base_url,
        *[s.strip() for s in settings.cors_origins.split(",")],
    }
    origin = request.headers.get("origin")
    if (origin and origin not in allowed) or request.headers.get(
        "sec-fetch-site"
    ) == "cross-site":
        raise HTTPException(403, "Недопустимый источник запроса")


def digest(value):
    return sha256(value.encode()).hexdigest()


def forget_session(db, request: Request, response: Response):
    raw = request.cookies.get(COOKIE)
    if raw:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(raw)))
    response.delete_cookie(
        COOKIE,
        path="/api/auth",
        httponly=True,
        samesite="strict",
        secure=settings.public_base_url.startswith("https://"),
    )
    response.headers["Cache-Control"] = "no-store"


def create_session(db, user, request: Request, response: Response):
    forget_session(db, request, response)
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    raw = secrets.token_urlsafe(48)
    db.add(
        LoginSession(
            token_hash=digest(raw),
            user_id=user.id,
            expires_at=now() + timedelta(seconds=MAX_AGE),
        )
    )
    response.set_cookie(
        COOKIE,
        raw,
        max_age=MAX_AGE,
        path="/api/auth",
        httponly=True,
        samesite="strict",
        secure=settings.public_base_url.startswith("https://"),
    )
    return digest(raw)


def session_user(db, request: Request):
    from app.models import User

    raw = request.cookies.get(COOKIE)
    session = db.get(LoginSession, digest(raw)) if raw else None
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= now():
        raise HTTPException(401, "Сессия истекла. Войдите снова")
    user = db.get(User, session.user_id)
    if not user or not user.roles:
        raise HTTPException(401, "Сессия недоступна")
    return user, session.token_hash
