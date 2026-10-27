from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, LoginSession, now

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()


def token(user: User, session_id: str | None = None):
    return jwt.encode(
        {
            "sub": str(user.id),
            **({"sid": session_id} if session_id else {}),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_minutes),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


@dataclass
class Actor:
    user: User
    role: str


def current_actor(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    x_active_role: str | None = Header(None),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=["HS256"]
        )
        user = db.get(User, int(payload["sub"]))
        if payload.get("sid"):
            session = db.get(LoginSession, payload["sid"])
            if (
                not session
                or session.user_id != int(payload["sub"])
                or session.expires_at.replace(tzinfo=timezone.utc) <= now()
            ):
                raise HTTPException(401, "Сессия завершена. Войдите снова")
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Сессия истекла. Войдите снова")
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    roles = [r.id for r in user.roles]
    role = x_active_role or (roles[0] if roles else "")
    if role not in roles:
        raise HTTPException(403, "Активная роль недоступна")
    return Actor(user, role)


def allow(*roles):
    def check(actor: Actor = Depends(current_actor)):
        if actor.role not in roles:
            raise HTTPException(403, "Нет прав в активной роли")
        return actor

    return check
