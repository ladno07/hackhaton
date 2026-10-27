"""Account linking shared by the website and the standalone bot."""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta, timezone
from sqlalchemy import delete, func, select
from fastapi import HTTPException
from app.config import settings
from app.models import Notification, TelegramCodeAttempt, TelegramDelivery, TelegramLink, TelegramLinkToken, User, now


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def enabled():
    return bool(settings.telegram_bot_token and settings.telegram_bot_username)


def digest(token):
    # Numeric codes have low entropy; a keyed hash prevents offline enumeration of a DB dump.
    return hmac.new(settings.jwt_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def normalize_code(code):
    return re.sub(r"[\s-]", "", code.strip())


def record_attempt(db, chat_id, at):
    entry = db.scalar(select(TelegramCodeAttempt).where(TelegramCodeAttempt.chat_id == chat_id).with_for_update())
    if not entry:
        entry = TelegramCodeAttempt(chat_id=chat_id, attempts=0, window_started_at=at)
        db.add(entry)
    elif utc(at) >= utc(entry.window_started_at) + timedelta(minutes=10):
        entry.attempts, entry.window_started_at = 0, at
    if entry.attempts >= 5:
        raise ValueError("Слишком много попыток. Повторите через 10 минут после начала ввода кодов.")
    entry.attempts += 1
    db.flush()


def disconnect(db, link):
    if link:
        link.active = False
        link.chat_id = None
        link.blocked_at = None
        for delivery in db.scalars(select(TelegramDelivery).where(
            TelegramDelivery.link_id == link.id, TelegramDelivery.status == "pending"
        )):
            delivery.status = "cancelled"
        db.execute(delete(TelegramLinkToken).where(TelegramLinkToken.user_id == link.user_id))


def issue(db, user_id, at=None):
    if not enabled():
        raise HTTPException(503, "Telegram-бот пока не настроен")
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == user_id))
    if link and (link.active or link.chat_id is not None):
        raise HTTPException(409, "Сначала отключите текущую привязку")
    for _ in range(20):
        token = f"{secrets.randbelow(100_000_000):08d}"
        if not db.scalar(select(TelegramLinkToken.user_id).where(TelegramLinkToken.token_hash == digest(token))):
            break
    else:
        raise HTTPException(503, "Не удалось создать код. Повторите запрос.")
    expires = (at or now()) + timedelta(minutes=10)
    db.execute(delete(TelegramLinkToken).where(TelegramLinkToken.user_id == user_id))
    db.add(TelegramLinkToken(user_id=user_id, token_hash=digest(token), expires_at=expires))
    db.flush()
    return {"code": token, "bot_url": f"https://t.me/{settings.telegram_bot_username.lstrip('@')}", "expires_at": expires}


def claim(db, token, chat_id, confirm=False, at=None):
    at = at or now()
    if not confirm:
        record_attempt(db, chat_id, at)
    token = normalize_code(token)
    if not re.fullmatch(r"[0-9]{8}", token):
        raise ValueError("Введите 8 цифр кода, полученного на сайте в разделе «Уведомления».")
    obj = db.scalar(select(TelegramLinkToken).where(
        TelegramLinkToken.token_hash == digest(token)
    ).with_for_update())
    if not obj or utc(obj.expires_at) <= utc(at):
        raise ValueError("Код неверный, истёк или уже использован. Получите новый на сайте.")
    if obj.chat_id not in (None, chat_id):
        raise ValueError("Этот код уже введён в другом Telegram-аккаунте.")
    existing = db.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id))
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == obj.user_id))
    if existing or (link and link.active):
        raise ValueError("Аккаунт уже привязан. Сначала отключите существующую привязку.")
    user = db.get(User, obj.user_id)
    roles = sorted(r.id for r in user.roles)
    if not roles:
        raise ValueError("У аккаунта нет доступных ролей.")
    if not confirm:
        obj.chat_id = chat_id
        db.flush()
        return user
    if obj.chat_id != chat_id:
        raise ValueError("Сначала отправьте боту код подключения с сайта.")
    if not link:
        link = TelegramLink(user_id=user.id)
        db.add(link)
    link.chat_id, link.active, link.blocked_at = chat_id, True, None
    link.role, link.connected_at = roles[0], at
    link.baseline_id = db.scalar(select(func.max(Notification.id))) or 0
    db.delete(obj)
    db.flush()
    from app.security import Actor
    from app.services.common import audit
    audit(db, Actor(user, link.role), "Подключение Telegram", link)
    return link
