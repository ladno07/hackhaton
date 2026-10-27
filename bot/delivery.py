"""Independent Telegram outbox, with live authorization before every attempt."""
from datetime import timedelta
from sqlalchemy import select
from fastapi import HTTPException
from app.models import (
    Competition, CompetitionApplication, CompetitionJudge, CompetitionResult, Judge,
    Notification, RankApplication, TelegramCursor, TelegramDelivery, TelegramLink, User, now,
)
from app.security import Actor
from app.services.notifications import visible_in_role
from app.services.telegram_link import utc
from bot.schedule import athlete_audience, competition_audience, current_reminders, roles_for
from bot.telegram import TelegramError
from bot.views import ROLE_NAMES, button


def notice_roles(db, notice, reminders):
    # Recheck legacy queued messages as well as newly scheduled reminders.
    context_roles = (notice.telegram_context or {}).get("roles")
    if context_roles is not None and "athlete" not in context_roles:
        return set()
    return _notice_roles(db, notice, reminders) & {"athlete"}


def _notice_roles(db, notice, reminders):
    key = notice.event_key
    if key.startswith("tg-reminder:"):
        current = reminders.get((notice.user_id, key))
        return current.roles if current else set()
    if key.startswith("deadline:"):
        # Legacy in-app/email summaries; the bot uses the precise schedule instead.
        return set()
    parts = key.split(":")
    user = db.get(User, notice.user_id)
    available = roles_for(db, user.id)
    if parts[0] in ("application-decision", "protocol", "rank-decision"):
        if parts[0] == "application-decision":
            app = db.get(CompetitionApplication, int(parts[1]))
            comp = db.get(Competition, app.competition_id) if app else None
            athlete_id = app.athlete_id if app else None
        elif parts[0] == "protocol":
            comp = db.get(Competition, int(parts[1]))
            athlete_id = int(parts[2])
        else:
            app = db.get(RankApplication, int(parts[1]))
            if not app:
                return set()
            if app.judge_id:
                judge = db.get(Judge, app.judge_id)
                return {"judge"} & available if judge and judge.user_id == user.id else set()
            result = db.get(CompetitionResult, app.result_id)
            comp = db.get(Competition, result.competition_id) if result else None
            athlete_id = app.athlete_id
        return athlete_audience(db, athlete_id, comp.discipline_id).get(user.id, set()) & available if comp else set()
    if parts[0] == "judge":
        judge = db.get(Judge, int(parts[2]))
        assignment = db.get(CompetitionJudge, (int(parts[1]), int(parts[2])))
        return {"judge"} & available if assignment and judge and judge.user_id == user.id else set()
    if parts[0] in ("competition-schedule", "competition-regulation"):
        comp = db.get(Competition, int(parts[1]))
        if not comp or comp.state == "draft":
            return set()
        if parts[0] == "competition-schedule":
            # Old schedule-change messages should not be delivered after another move.
            if (notice.telegram_context or {}).get("schedule") != [str(comp.start_date), str(comp.end_date), str(comp.start_time), comp.timezone]:
                return set()
            return competition_audience(db, comp).get(user.id, set()) & available
        audience = {}
        for app in db.scalars(select(CompetitionApplication).where(
            CompetitionApplication.competition_id == comp.id, CompetitionApplication.status != "rejected"
        )):
            for uid, roles in athlete_audience(db, app.athlete_id, comp.discipline_id).items():
                audience.setdefault(uid, set()).update(roles)
        return audience.get(user.id, set()) & available
    result = set()
    for role in available:
        try:
            if visible_in_role(db, Actor(user, role), notice):
                result.add(role)
        except HTTPException:
            continue
    return result


def notice_path(db, notice):
    if notice.telegram_context:
        return notice.telegram_context.get("path", "/notifications")
    parts = notice.event_key.split(":")
    if parts[0] in ("protocol", "judge", "competition-open", "competition-regulation", "competition-schedule"):
        return f"/competitions/{parts[1]}"
    if parts[0] in ("application", "application-decision"):
        app = db.get(CompetitionApplication, int(parts[1]))
        if app:
            return f"/competitions/{app.competition_id}"
    return "/ranks" if parts[0].startswith("rank-") else "/notifications"


def prepare(db, at):
    for link in db.scalars(select(TelegramLink).where(TelegramLink.active.is_(True), TelegramLink.blocked_at.is_(None))):
        existing = select(TelegramDelivery.notification_id).where(TelegramDelivery.link_id == link.id)
        for notice in db.scalars(select(Notification).where(
            Notification.user_id == link.user_id, Notification.id > link.baseline_id,
            Notification.id.not_in(existing)
        ).order_by(Notification.id).limit(200)):
            db.add(TelegramDelivery(link_id=link.id, notification_id=notice.id, next_attempt_at=at))
    db.flush()


def deliver(db, api, at=None):
    at = at or now()
    cursor = db.get(TelegramCursor, 1)
    if cursor and cursor.send_after and utc(cursor.send_after) > utc(at):
        return
    prepare(db, at)
    reminders = current_reminders(db, at)
    pending = db.scalars(select(TelegramDelivery).where(
        TelegramDelivery.status == "pending", TelegramDelivery.next_attempt_at <= at
    ).order_by(TelegramDelivery.next_attempt_at, TelegramDelivery.id).limit(100)).all()
    for delivery in pending:
        # Keep the link row locked until the send is recorded; disconnect waits for this attempt.
        link = db.scalar(select(TelegramLink).where(TelegramLink.id == delivery.link_id).with_for_update())
        notice = db.get(Notification, delivery.notification_id)
        roles = notice_roles(db, notice, reminders) if link and link.active else set()
        reminder = reminders.get((notice.user_id, notice.event_key))
        if reminder and link and utc(reminder.scheduled_at) < utc(link.connected_at):
            roles = set()
        if not roles or not link.chat_id or link.blocked_at or notice.id <= link.baseline_id:
            delivery.status = "cancelled"
            db.commit()
            continue
        delivery.attempts += 1
        text = " / ".join(ROLE_NAMES[r] for r in sorted(roles)) + "\n" + notice.title + "\n\n" + notice.body
        try:
            api.send(link.chat_id, text, [[button("Открыть на сайте", path=notice_path(db, notice))]])
            delivery.status, delivery.sent_at, delivery.last_error = "sent", at, None
        except TelegramError as exc:
            delivery.last_error = str(exc)
            if exc.code == 403:
                link.blocked_at = at
                link.active = False
                delivery.status = "blocked"
                for other in db.scalars(select(TelegramDelivery).where(
                    TelegramDelivery.link_id == link.id, TelegramDelivery.status == "pending"
                )):
                    other.status = "cancelled"
            elif exc.code in (400, 401, 404):
                delivery.status = "failed"
            else:
                delay = exc.retry_after or min(1800, 30 * 2 ** min(delivery.attempts - 1, 6))
                delivery.next_attempt_at = at + timedelta(seconds=delay)
                if exc.code == 429:
                    cursor = db.get(TelegramCursor, 1)
                    if not cursor:
                        cursor = TelegramCursor(id=1, update_id=-1)
                        db.add(cursor)
                    cursor.send_after = delivery.next_attempt_at
                db.commit()
                if exc.code == 429:
                    # Telegram can apply a bot-wide limit; do not hammer other recipients.
                    break
                continue
        db.commit()
