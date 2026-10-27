import asyncio
import logging
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import *

logger = logging.getLogger(__name__)


def notify(db, user_ids, title, body, key):
    for user_id in set(user_ids):
        if not db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id, Notification.event_key == key
            )
        ):
            db.add(Notification(user_id=user_id, title=title, body=body, event_key=key))
    db.flush()


def admins(db):
    return db.scalars(select(UserRole.user_id).where(UserRole.role_id == "admin")).all()


def athlete_audience(db, athlete_id):
    athlete = db.get(Athlete, athlete_id)
    coaches = db.scalars(
        select(Coach.user_id)
        .join(AthleteCoach, AthleteCoach.coach_id == Coach.id)
        .where(AthleteCoach.athlete_id == athlete_id, AthleteCoach.status == "active")
    ).all()
    return [athlete.user_id, *coaches]


def deadlines(db):
    today = date.today()
    for comp in db.scalars(
        select(Competition).where(
            Competition.state == "open",
            Competition.deadline >= today,
            Competition.deadline <= today + timedelta(days=7),
        )
    ):
        notify(
            db,
            db.scalars(select(User.id)).all(),
            "Завершается приём заявок",
            f"{comp.title}: до {comp.deadline}",
            f"deadline:comp:{comp.id}:{comp.deadline}",
        )
    for rank in db.scalars(
        select(SportsRank).where(
            SportsRank.expires_on >= today,
            SportsRank.expires_on <= today + timedelta(days=30),
        )
    ):
        notify(
            db,
            [*admins(db), *athlete_audience(db, rank.athlete_id)],
            "Истекает спортивный разряд",
            f"{rank.name}, срок: {rank.expires_on}",
            f"deadline:rank:{rank.id}:{rank.expires_on}",
        )
    for cat in db.scalars(
        select(JudgeCategory).where(
            JudgeCategory.expires_on >= today,
            JudgeCategory.expires_on <= today + timedelta(days=30),
        )
    ):
        notify(
            db,
            [*admins(db), db.get(Judge, cat.judge_id).user_id],
            "Истекает судейская категория",
            f"{cat.name}, срок: {cat.expires_on}",
            f"deadline:category:{cat.id}:{cat.expires_on}",
        )
    for item in db.scalars(
        select(Deadline).where(
            Deadline.done == False,
            Deadline.due_on >= today,
            Deadline.due_on <= today + timedelta(days=30),
        )
    ):
        notify(
            db,
            admins(db),
            "Приближается срок",
            f"{item.title}: {item.due_on}",
            f"deadline:custom:{item.id}:{item.due_on}",
        )
    feb = date(today.year if today.month == 1 else today.year + 1, 2, 1)
    if 0 <= (feb - today).days <= 30:
        notify(
            db,
            admins(db),
            "Ходатайства на премии Губернатора",
            f"Срок подачи: {feb}",
            f"deadline:governor:{feb.year}",
        )


def deliver(db):
    pending = db.scalars(
        select(Notification)
        .where(Notification.mailed_at.is_(None))
        .order_by(Notification.id)
        .limit(50)
    ).all()
    if not pending:
        return
    for notice in pending:
        notice.attempts += 1
        try:
            message = EmailMessage()
            message["From"] = settings.mail_from
            message["To"] = db.get(User, notice.user_id).email
            message["Subject"] = notice.title
            message["Message-ID"] = f"<notification-{notice.id}@orencode.test>"
            message.set_content(notice.body)
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=5
            ) as smtp:
                if settings.smtp_tls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
            notice.mailed_at = now()
            notice.last_error = None
        except Exception as exc:
            notice.last_error = str(exc)[:1000]
            logger.warning(
                "Notification %s delivery failed: %s", notice.id, type(exc).__name__
            )
            break
    db.commit()


def tick():
    with SessionLocal() as db:
        deadlines(db)
        db.commit()
        deliver(db)


async def worker():
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:
            logger.exception("Notification worker iteration failed")
        await asyncio.sleep(60)


# Public calendar events; personal and internal federation events stay hidden.
MINISTRY_EVENTS = {"competition-open", "competition-regulation"}


def visible_in_role(db, actor, notice):
    """Account ownership is checked by the router; this additionally scopes role-specific events."""
    if actor.role == "admin":
        return True
    from app.services.common import visible_athletes, own

    parts = notice.event_key.split(":")
    kind = parts[0]
    if actor.role == "ministry":
        return kind in MINISTRY_EVENTS or notice.event_key.startswith("deadline:comp:")
    if kind in {"application", "rank-application"}:
        return False
    if kind == "deadline":
        if parts[1] in {"custom", "governor"}:
            return False
        if parts[1] == "rank":
            rank = db.get(SportsRank, int(parts[2]))
            return bool(rank and rank.athlete_id in visible_athletes(db, actor))
        if parts[1] == "category":
            cat = db.get(JudgeCategory, int(parts[2]))
            return bool(
                actor.role == "judge"
                and cat
                and cat.judge_id == own(db, Judge, actor).id
            )
    if kind in {"link", "link-change"}:
        link = db.get(AthleteCoach, int(parts[1]))
        if not link:
            return False
        if actor.role == "athlete":
            return link.athlete_id == own(db, Athlete, actor).id
        if actor.role == "coach":
            return link.coach_id == own(db, Coach, actor).id
        return False
    if kind == "application-decision":
        application = db.get(CompetitionApplication, int(parts[1]))
        return bool(
            application and application.athlete_id in visible_athletes(db, actor)
        )
    if kind == "protocol":
        return int(parts[2]) in visible_athletes(db, actor)
    if kind == "judge":
        return actor.role == "judge" and int(parts[2]) == own(db, Judge, actor).id
    if kind == "rank-decision":
        application = db.get(RankApplication, int(parts[1]))
        if not application:
            return False
        if application.judge_id:
            return (
                actor.role == "judge"
                and application.judge_id == own(db, Judge, actor).id
            )
        return application.athlete_id in visible_athletes(db, actor)
    return True
