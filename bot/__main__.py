"""Run with python -m bot, with the repository and backend on PYTHONPATH."""
import logging
import time
from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.config import settings
from app.db import SessionLocal, engine
from app.models import TelegramCursor
from bot.telegram import Telegram, TelegramError
from bot.handlers import handle
from bot.navigation import reply_screen
from bot.schedule import schedule
from bot.delivery import deliver

log = logging.getLogger("fsp.bot")
COMMANDS = [{"command": "start", "description": "Открыть меню"}]


def process_update(db, api, update):
    """Permanent failures acknowledge the update so one bad button cannot block the queue."""
    feedback = None
    try:
        handle(db, api, update)
    except TelegramError as exc:
        db.rollback()
        if exc.code not in (400, 403, 404):
            raise  # Transient failures keep the cursor unchanged for retry.
        log.warning("Update rejected: code=%s method=%s reason=%s", exc.code, exc.method, exc.reason)
        if exc.code != 403:
            feedback = "Не удалось открыть этот раздел. Попробуйте /start, чтобы обновить меню."
    except (IntegrityError, HTTPException):
        db.rollback()
        feedback = "Данные изменились. Откройте /start и повторите действие. Для привязки получите новый код на сайте."
    except Exception as exc:
        db.rollback()
        # Do not log update bodies, pairing codes or token-bearing HTTP URLs.
        log.error("Update handler failed: %s", type(exc).__name__)
        feedback = "Не удалось обработать действие. Откройте /start и попробуйте ещё раз."
    if feedback:
        callback = update.get("callback_query", {})
        message = callback.get("message") or update.get("message") or {}
        chat, sender = message.get("chat", {}), (callback or message).get("from", {})
        if chat.get("type") == "private" and chat.get("id") == sender.get("id"):
            try:
                reply_screen(api, chat["id"], feedback,
                             previous_message_id=message.get("message_id") if callback else None)
            except TelegramError as exc:
                if exc.code not in (400, 403, 404):
                    raise
    cursor = db.get(TelegramCursor, 1)
    if not cursor:
        cursor = TelegramCursor(id=1, update_id=-1)
        db.add(cursor)
    cursor.update_id = max(cursor.update_id, update["update_id"])
    db.commit()


@contextmanager
def singleton():
    # Session-level PostgreSQL lock survives commits in work sessions.
    with engine.connect() as connection:
        if connection.dialect.name != "postgresql":
            raise RuntimeError("The standalone bot requires PostgreSQL for its single-process lock")
        if not connection.scalar(text("SELECT pg_try_advisory_lock(734901271)")):
            raise RuntimeError("Another bot process already holds the polling lock")
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(734901271)"))


def run():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not settings.telegram_bot_token or not settings.telegram_bot_username:
        log.error("Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME to enable the bot")
        return
    api = Telegram()
    try:
        with singleton():
            api.call("setMyCommands", commands=COMMANDS)
            with SessionLocal() as db:
                if not db.get(TelegramCursor, 1):
                    db.add(TelegramCursor(id=1, update_id=-1))
                    db.commit()
            next_tick = 0
            while True:
                try:
                    if time.monotonic() >= next_tick:
                        try:
                            with SessionLocal() as db:
                                schedule(db)
                                db.commit()
                                deliver(db, api)
                        except Exception as exc:
                            log.error("Notification tick failed: %s", type(exc).__name__)
                        next_tick = time.monotonic() + 60
                    with SessionLocal() as db:
                        offset = db.get(TelegramCursor, 1).update_id + 1
                    updates = api.call("getUpdates", offset=offset, timeout=20,
                                       allowed_updates=["message", "callback_query"])
                    for update in updates:
                        with SessionLocal() as db:
                            process_update(db, api, update)
                except TelegramError as exc:
                    log.warning("Telegram request failed: code %s", exc.code)
                    time.sleep(min(60, exc.retry_after or 5))
                except Exception:
                    # Avoid logging raw HTTP exceptions that can contain bot tokens.
                    log.error("Bot iteration failed; inspect database and configuration")
                    time.sleep(5)
    finally:
        api.close()


if __name__ == "__main__":
    run()
