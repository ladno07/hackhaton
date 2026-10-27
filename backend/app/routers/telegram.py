from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import TelegramLink, TelegramLinkToken
from app.security import current_actor, Actor
from app.services.telegram_link import enabled, issue, disconnect
from app.services.common import audit

router = APIRouter(prefix="/telegram", tags=["Telegram"])


@router.get("/link")
def status(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == actor.user.id))
    return {"available": enabled(), "connected": bool(link and link.active),
            "blocked": bool(link and link.blocked_at),
            "connected_at": link.connected_at if link else None}


@router.post("/link-token", deprecated=True)
@router.post("/link-code")
def create_token(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return issue(db, actor.user.id)


@router.delete("/link", status_code=204)
def remove_link(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == actor.user.id).with_for_update())
    disconnect(db, link)
    token = db.get(TelegramLinkToken, actor.user.id)
    if token:
        db.delete(token)
    if link:
        audit(db, actor, "Отключение Telegram", link)
