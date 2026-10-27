import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
# Marking own notifications as read is the only write a read-only role makes.
READ_MARKS = re.compile(r"/api/notifications/\d+/read")


def token(user: User):
    return jwt.encode(
        {
            "sub": str(user.id),
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
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    x_active_role: str | None = Header(None),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=["HS256"]
        )
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Сессия истекла. Войдите снова")
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    roles = [r.id for r in user.roles]
    role = x_active_role or (roles[0] if roles else "")
    if role not in roles:
        raise HTTPException(403, "Активная роль недоступна")
    # Ministry is read-only everywhere, even if an endpoint forgets to check roles.
    if role == "ministry" and request.method not in READ_METHODS:
        if not READ_MARKS.fullmatch(request.url.path):
            raise HTTPException(403, "Кабинет Минспорта доступен только для просмотра")
    return Actor(user, role)


def allow(*roles):
    def check(actor: Actor = Depends(current_actor)):
        if actor.role not in roles:
            raise HTTPException(403, "Нет прав в активной роли")
        return actor

    return check
