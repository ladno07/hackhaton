import asyncio
import logging
import smtplib
from fastapi import HTTPException
from datetime import date, timedelta
from email.message import EmailMessage
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import *
from app.services.competition_notifications import (
    admitted_athletes, competition_in_progress, registration_recipients, reminder_stage,
)
from app.services.telegram_link import utc

logger = logging.getLogger(__name__)


def link_change_content(db, link, status, recipient_role):
    title = {
        "active": "Связь подтверждена",
        "paused": "Связь приостановлена",
        "ended": "Связь завершена",
    }[status]
    discipline = db.get(Discipline, link.discipline_id)
    if recipient_role == "coach":
        athlete = db.get(Athlete, link.athlete_id)
        participant = f"Спортсмен: {athlete.user.full_name}"
    else:
        coach = db.get(Coach, link.coach_id)
        participant = f"Тренер: {coach.user.full_name}"
    body = f"{participant}\nНаправление: {discipline.short_name}"
    return title, body


def is_registration_notice(notice):
    parts = notice.event_key.split(":")
    return parts[0] == "competition-open" or parts[:2] in (
        ["deadline", "comp"], ["tg-reminder", "registration"])


def notify(db, user_ids, title, body, key, occurred_at=None):
    for user_id in set(user_ids):
        user = db.get(User, user_id)
        if occurred_at and (not user or utc(occurred_at) < utc(user.created_at)):
            continue
        if not db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id, Notification.event_key == key
            )
        ):
            db.add(Notification(user_id=user_id, title=title, body=body, event_key=key))
    db.flush()


def admins(db):
    return db.scalars(select(UserRole.user_id).where(UserRole.role_id == "admin")).all()


def athlete_audience(db, athlete_id, discipline_id=None):
    athlete = db.get(Athlete, athlete_id)
    query = (
        select(Coach.user_id)
        .join(AthleteCoach, AthleteCoach.coach_id == Coach.id)
        .where(AthleteCoach.athlete_id == athlete_id, AthleteCoach.status == "active", Coach.archived_at.is_(None))
    )
    if discipline_id is not None:
        query = query.where(AthleteCoach.discipline_id == discipline_id)
    coaches = db.scalars(query).all()
    return [athlete.user_id, *coaches]


def deadlines(db):
    from app.services.training_schedule import reminders
    reminders(db)
    today = date.today()
    for comp in db.scalars(
        select(Competition).where(
            Competition.state.in_(["open", "closed"]),
            Competition.end_date >= today,
            Competition.end_date <= today + timedelta(days=1),
        )
    ):
        stage = reminder_stage(comp.end_date, (1, 0), timezone=comp.timezone)
        if not stage or not competition_in_progress(comp):
            continue
        days, moment = stage
        notify(
            db,
            [uid for uid, since in admitted_athletes(db, comp).items() if utc(since) <= utc(moment)],
            "Соревнование завершается",
            f"{comp.title}: окончание {comp.end_date:%d.%m.%Y}",
            f"deadline:end:{comp.id}:{comp.end_date}:{days}",
            occurred_at=moment,
        )
    for rank in db.scalars(
        select(SportsRank).where(
            SportsRank.expires_on >= today,
            SportsRank.expires_on <= today + timedelta(days=30),
        )
    ):
        stage = reminder_stage(rank.expires_on, (30, 7, 1))
        if not stage:
            continue
        days, moment = stage
        notify(
            db,
            athlete_audience(db, rank.athlete_id, rank.discipline_id),
            "Истекает спортивный разряд",
            f"{rank.name}, срок: {rank.expires_on:%d.%m.%Y}",
            f"deadline:rank:{rank.id}:{rank.expires_on}:{days}",
            occurred_at=moment,
        )
    for cat in db.scalars(
        select(JudgeCategory).where(
            JudgeCategory.expires_on >= today,
            JudgeCategory.expires_on <= today + timedelta(days=30),
        )
    ):
        notify(
            db,
            [db.get(Judge, cat.judge_id).user_id],
            "Истекает судейская категория",
            f"{cat.name}, срок: {cat.expires_on:%d.%m.%Y}",
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
            f"{item.title}: {item.due_on:%d.%m.%Y}",
            f"deadline:custom:{item.id}:{item.due_on}",
        )
    feb = date(today.year if today.month == 1 else today.year + 1, 2, 1)
    if 0 <= (feb - today).days <= 30:
        notify(
            db,
            admins(db),
            "Ходатайства на премии Губернатора",
            f"Срок подачи: {feb:%d.%m.%Y}",
            f"deadline:governor:{feb.year}",
        )


def deliver(db):
    pending = db.scalars(
        select(Notification)
        .where(Notification.mailed_at.is_(None))
        .order_by(Notification.id)
    ).yield_per(50)
    attempts = 0
    for notice in pending:
        user = db.get(User, notice.user_id)
        from app.security import Actor
        if not any(visible_in_role(db, Actor(user, role.id), notice) for role in user.roles):
            continue
        if attempts >= 50:
            break
        attempts += 1
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
        from app.services.integrations import deliver_webhooks
        deliver_webhooks(db)


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
    parts = notice.event_key.split(":")
    if notice.event_key.startswith("training-"):
        from app.services.training_schedule import visible_training_notice
        return visible_training_notice(db, actor, notice)
    if parts[0] == "coach-chat":
        message = db.get(CoachChatMessage, int(parts[1]))
        link = db.get(AthleteCoach, message.link_id) if message else None
        athlete = db.get(Athlete, link.athlete_id) if link else None
        coach = db.get(Coach, link.coach_id) if link else None
        if not link or link.status != "active" or coach.archived_at:
            return False
        return ((actor.role == "athlete" and message.sender_role == "coach"
                 and actor.user.id == notice.user_id == athlete.user_id)
                or (actor.role == "coach" and message.sender_role == "athlete"
                    and actor.user.id == notice.user_id == coach.user_id))
    if actor.role == "ministry":
        return parts[0] in MINISTRY_EVENTS or notice.event_key.startswith("deadline:comp:")
    if is_registration_notice(notice):
        if actor.role != "athlete" or parts[0] != "competition-open":
            return False
        comp = db.get(Competition, int(parts[1] if parts[0] == "competition-open" else parts[2]))
        return bool(comp and actor.user.id in registration_recipients(
            db, comp, exclude_applied=parts[0] != "competition-open"))
    if actor.role == "admin":
        if parts[0] == "deadline":
            return parts[1] in {"custom", "governor"}
        if parts[0] == "tg-reminder":
            return parts[1] in {"report", "governor"}
        return parts[0] not in {"application-decision", "rank-decision", "judge", "judge-removed", "protocol",
                                 "appeal-decision", "violation", "violation-cancel", "stage-transfer",
                                 "competition-schedule", "competition-regulation", "link", "link-change"}
    from app.services.common import visible_athletes, own

    def follows(athlete_id, discipline_id):
        from app.services.common import can_athlete
        try:
            can_athlete(db, actor, athlete_id, discipline_id)
            return True
        except HTTPException:
            return False

    parts = notice.event_key.split(":")
    kind = parts[0]
    if kind == "passport-consent":
        return False
    if kind == "passport-consent-decision":
        return actor.role == "athlete"
    if kind == "competition-team":
        return actor.role in {"athlete", "coach"}
    if kind == "tg-reminder":
        if actor.role not in (notice.telegram_context or {}).get("roles", []):
            return False
        family, entity_id = parts[1], int(parts[2])
        if family in {"report", "governor"}:
            return False
        if family == "category":
            category = db.get(JudgeCategory, entity_id)
            return bool(category and actor.role == "judge" and category.judge_id == own(db, Judge, actor).id)
        if family == "rank":
            rank = db.get(SportsRank, entity_id)
            if not rank:
                return False
            from app.services.common import can_athlete
            try:
                can_athlete(db, actor, rank.athlete_id, rank.discipline_id)
                return True
            except HTTPException:
                return False
        comp = db.get(Competition, entity_id)
        if not comp:
            return False
        from zoneinfo import ZoneInfo
        if comp.state not in ("open", "closed") or now().astimezone(ZoneInfo(comp.timezone)).date() > comp.end_date:
            return False
        if family == "end" and not competition_in_progress(comp):
            return False
        if actor.role == "judge":
            return bool(family == "start" and db.get(CompetitionJudge, (comp.id, own(db, Judge, actor).id)))
        # Only active links in the competition's discipline give coaches access.
        athletes = visible_athletes(db, actor)
        if actor.role == "coach":
            athletes = set(db.scalars(select(AthleteCoach.athlete_id).where(
                AthleteCoach.coach_id == own(db, Coach, actor).id,
                AthleteCoach.status == "active", AthleteCoach.discipline_id == comp.discipline_id)))
        if family in {"start", "end"}:
            if family == "end" and actor.role != "athlete":
                return False
            return bool(db.scalar(select(CompetitionApplication.id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.athlete_id.in_(athletes), CompetitionApplication.status == "approved")))
        return bool(athletes)
    if kind in {"application", "rank-application", "appeal"}:
        return False
    if kind == "appeal-decision":
        appeal = db.get(Appeal, int(parts[1]))
        comp = db.get(Competition, appeal.competition_id) if appeal and appeal.competition_id else None
        return bool(appeal and follows(appeal.athlete_id, comp.discipline_id if comp else None))
    if kind in {"violation", "violation-cancel"}:
        violation = db.get(Violation, int(parts[1]))
        return bool(violation and follows(violation.athlete_id, None))
    if kind in {"stage-ready", "stage-transfer"}:
        transfer = db.get(StageTransfer, int(parts[1])) if kind == "stage-transfer" else None
        athlete_id = transfer.athlete_id if transfer else int(parts[1])
        return bool((transfer or kind == "stage-ready") and follows(athlete_id, None))
    if kind == "deadline":
        if parts[1] == "end":
            comp = db.get(Competition, int(parts[2]))
            return bool(actor.role == "athlete" and comp and competition_in_progress(comp)
                        and actor.user.id in admitted_athletes(db, comp))
        if parts[1] in {"custom", "governor"}:
            return False
        if parts[1] == "rank":
            rank = db.get(SportsRank, int(parts[2]))
            return bool(rank and follows(rank.athlete_id, rank.discipline_id))
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
        comp = db.get(Competition, application.competition_id) if application else None
        return bool(
            comp and follows(application.athlete_id, comp.discipline_id)
        )
    if kind == "protocol":
        comp = db.get(Competition, int(parts[1]))
        return bool(comp and follows(int(parts[2]), comp.discipline_id))
    if kind in {"competition-schedule", "competition-regulation"}:
        comp = db.get(Competition, int(parts[1]))
        if not comp or comp.state == "draft":
            return False
        if actor.role == "judge":
            return bool(kind == "competition-schedule" and db.get(CompetitionJudge, (comp.id, own(db, Judge, actor).id)))
        return any(follows(app.athlete_id, comp.discipline_id) for app in db.scalars(select(CompetitionApplication).where(
            CompetitionApplication.competition_id == comp.id,
            CompetitionApplication.status == "approved" if kind == "competition-schedule" else CompetitionApplication.status != "rejected")))
    if kind in {"judge", "judge-removed"}:
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
        result = db.get(CompetitionResult, application.result_id)
        comp = db.get(Competition, result.competition_id) if result else None
        return bool(comp and follows(application.athlete_id, comp.discipline_id))
    return True
