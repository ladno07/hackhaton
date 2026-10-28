"""Shared lesson lifecycle, local time, audiences and delivery authorization."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Athlete, Coach, GroupEnrollment, LessonAttendance, Notification, TrainingGroup, TrainingLesson, now
from app.services.common import row


def interval(lesson):
    if lesson.start_time is None or lesson.format == "correspondence":
        return None, None
    start = datetime.combine(lesson.held_on, lesson.start_time, ZoneInfo(lesson.timezone)).astimezone(timezone.utc)
    return start, start + timedelta(minutes=lesson.duration_minutes)


def lesson_view(lesson):
    start, end = interval(lesson)
    phase = lesson.status
    if phase == "planned" and lesson.format == "correspondence":
        today = now().astimezone(ZoneInfo(lesson.timezone)).date()
        phase = "not_started" if today < lesson.held_on else "deadline_passed" if lesson.due_on and today > lesson.due_on else "self_study"
    elif phase == "planned":
        phase = "upcoming" if now() < start else "in_progress" if now() < end else "awaiting_completion"
    return {**row(lesson), "starts_at": start, "ends_at": end, "phase": phase}


def roster(db, group_id, on):
    return set(db.scalars(select(GroupEnrollment.athlete_id).where(
        GroupEnrollment.group_id == group_id, GroupEnrollment.start_date <= on,
        (GroupEnrollment.end_date.is_(None) | (GroupEnrollment.end_date >= on)),
    )))


def check_conflicts(db, group, lesson):
    if db.bind.dialect.name == "postgresql":
        # Serialize planning so concurrent requests cannot book the same coach.
        db.execute(text("SELECT pg_advisory_xact_lock(204321001)"))
    start, end = interval(lesson)
    if start is None:
        return
    participants = roster(db, group.id, lesson.held_on)
    for other, other_group in db.execute(select(TrainingLesson, TrainingGroup)
        .join(TrainingGroup, TrainingGroup.id == TrainingLesson.group_id)
        .where(TrainingLesson.status != "cancelled", TrainingLesson.start_time.is_not(None),
               TrainingLesson.held_on >= lesson.held_on - timedelta(days=2),
               TrainingLesson.held_on <= lesson.held_on + timedelta(days=2))):
        if other.id == lesson.id:
            continue
        other_start, other_end = interval(other)
        if start < other_end and other_start < end:
            if group.id == other_group.id or group.coach_id == other_group.coach_id:
                raise HTTPException(409, "В это время у группы или тренера уже есть занятие")
            if participants & roster(db, other_group.id, other.held_on):
                raise HTTPException(409, "У одного из спортсменов в это время уже есть занятие в другой группе")


def lesson_notice(db, lesson, title, kind):
    from app.services.notifications import notify
    group = db.get(TrainingGroup, lesson.group_id)
    start, end = interval(lesson)
    when = (f"{start.astimezone(ZoneInfo(lesson.timezone)):%d.%m.%Y %H:%M}–"
            f"{end.astimezone(ZoneInfo(lesson.timezone)):%H:%M} ({lesson.timezone})" if start else f"{lesson.held_on:%d.%m.%Y}")
    if lesson.format == "correspondence":
        when = f"Заочно · начало {lesson.held_on:%d.%m.%Y}, выполнить до {lesson.due_on:%d.%m.%Y} ({lesson.timezone})"
    where = " · ".join(v for v in (lesson.location, lesson.meeting_url) if v)
    body = f"{group.name}\n{lesson.topic}\n{when}\n{where}"
    if kind == "cancelled":
        body += f"\nПричина: {lesson.cancellation_reason}"
    recipients = {db.get(Athlete, aid).user_id for aid in roster(db, group.id, lesson.held_on)}
    coach = db.get(Coach, group.coach_id)
    recipients.add(coach.user_id)
    key = f"training-lesson:{lesson.id}:{lesson.revision}:{kind}"
    notify(db, recipients, title, body, key)
    for n in db.scalars(select(Notification).where(Notification.event_key == key)):
        roles = ["athlete"] if n.user_id != coach.user_id else ["coach"]
        if n.user_id == coach.user_id and any(db.get(Athlete, aid).user_id == n.user_id for aid in roster(db, group.id, lesson.held_on)):
            roles.append("athlete")
        n.telegram_context = {"path": f"/training?group={group.id}", "roles": roles, "lesson_id": lesson.id, "revision": lesson.revision}


def enrollment_notice(db, enrollment, title):
    from app.services.notifications import notify
    group = db.get(TrainingGroup, enrollment.group_id)
    athlete = db.get(Athlete, enrollment.athlete_id)
    key = f"training-enrollment:{enrollment.id}:{'ended' if enrollment.end_date else 'enrolled'}"
    notify(db, [athlete.user_id], title, f"{group.name}\nТренер: {db.get(Coach, group.coach_id).user.full_name}\nРасписание и указания к занятиям — в разделе «Группы и занятия».", key)
    notice = db.scalar(select(Notification).where(Notification.event_key == key, Notification.user_id == athlete.user_id))
    notice.telegram_context = {"path": f"/training?group={group.id}", "roles": ["athlete"]}


def coach_assignment_notice(db, group):
    from app.services.notifications import notify
    coach = db.get(Coach, group.coach_id)
    key = f"training-coach:{group.id}:{now().isoformat()}"
    notify(db, [coach.user_id], "Вам назначена учебная группа", f"{group.name}\nОткройте группу, проверьте состав и запланируйте первое занятие с временем и местом проведения.", key)
    notice = db.scalar(select(Notification).where(Notification.event_key == key, Notification.user_id == coach.user_id))
    notice.telegram_context = {"path": f"/training?group={group.id}", "roles": ["coach"]}


def visible_training_notice(db, actor, notice):
    context = notice.telegram_context or {}
    if actor.user.id != notice.user_id or actor.role not in context.get("roles", []):
        return False
    if context.get("attendance_id"):
        attendance = db.get(LessonAttendance, context["attendance_id"])
        if not attendance or attendance.confirmed_at:
            return False
        if notice.event_key.startswith("training-dispute:"):
            lesson = db.get(TrainingLesson, attendance.lesson_id)
            group = db.get(TrainingGroup, lesson.group_id)
            coach = db.get(Coach, group.coach_id)
            return bool(attendance.dispute_reason and not coach.archived_at and coach.user_id == actor.user.id)
        return not attendance.dispute_reason and attendance.status == context.get("status")
    if notice.event_key.startswith("training-lesson:"):
        lesson = db.get(TrainingLesson, context.get("lesson_id"))
        if not lesson or lesson.revision != context.get("revision"):
            return False
        group = db.get(TrainingGroup, lesson.group_id)
        if actor.role == "coach":
            coach = db.get(Coach, group.coach_id)
            return coach.user_id == actor.user.id and not coach.archived_at
        return any(db.get(Athlete, aid).user_id == actor.user.id for aid in roster(db, group.id, lesson.held_on))
    return True


def reminders(db):
    for lesson in db.scalars(select(TrainingLesson).where(TrainingLesson.status == "planned", TrainingLesson.start_time.is_not(None))):
        start, _ = interval(lesson)
        if timedelta(0) < start - now() <= timedelta(hours=1):
            lesson_notice(db, lesson, "Занятие начнётся в течение часа", "reminder")
    for lesson in db.scalars(select(TrainingLesson).where(TrainingLesson.status == "planned", TrainingLesson.format == "correspondence", TrainingLesson.due_on.is_not(None))):
        today = now().astimezone(ZoneInfo(lesson.timezone)).date()
        if 0 <= (lesson.due_on - today).days <= 1:
            lesson_notice(db, lesson, "Приближается срок заочного задания", "due-reminder")
