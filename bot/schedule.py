"""Pure reminder selection, with an injectable clock and current audience checks."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models import (
    Athlete, AthleteCoach, Coach, Competition, CompetitionApplication,
    CompetitionJudge, Deadline, Judge, JudgeCategory, Notification, SportsRank, User, UserRole, now,
)
from app.services.competition_notifications import admitted_athletes, competition_in_progress
from app.services.notifications import notify
from app.services.telegram_link import utc

REGION = ZoneInfo("Asia/Yekaterinburg")


def roles_for(db, user_id):
    user = db.get(User, user_id)
    if not user:
        return set()
    roles = set(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id))) - {"ministry"}
    for role, model in (("coach", Coach), ("judge", Judge)):
        card = db.scalar(select(model).where(model.user_id == user_id))
        if role in roles and (not card or card.archived_at):
            roles.discard(role)
    if "athlete" in roles and not db.scalar(select(Athlete.id).where(Athlete.user_id == user_id)):
        roles.discard("athlete")
    return roles


def athlete_audience(db, athlete_id, discipline_id):
    """Map recipients to the roles through which they have access."""
    result = {}
    athlete = db.get(Athlete, athlete_id)
    if athlete and "athlete" in roles_for(db, athlete.user_id):
        result[athlete.user_id] = {"athlete"}
    for coach in db.scalars(select(Coach).join(AthleteCoach, AthleteCoach.coach_id == Coach.id).where(
        AthleteCoach.athlete_id == athlete_id, AthleteCoach.discipline_id == discipline_id,
        AthleteCoach.status == "active", Coach.archived_at.is_(None)
    )):
        if "coach" in roles_for(db, coach.user_id):
            result.setdefault(coach.user_id, set()).add("coach")
    return result


def merge(target, source):
    for user_id, roles in source.items():
        target.setdefault(user_id, set()).update(roles)
    return target


def admins(db):
    return {u.id: {"admin"} for u in db.scalars(select(User)) if "admin" in roles_for(db, u.id)}


def competition_audience(db, comp):
    result = {}
    for app in db.scalars(select(CompetitionApplication).where(
        CompetitionApplication.competition_id == comp.id, CompetitionApplication.status == "approved"
    )):
        merge(result, athlete_audience(db, app.athlete_id, comp.discipline_id))
    for judge in db.scalars(select(Judge).join(CompetitionJudge, CompetitionJudge.judge_id == Judge.id).where(
        CompetitionJudge.competition_id == comp.id, Judge.archived_at.is_(None)
    )):
        if "judge" in roles_for(db, judge.user_id):
            result.setdefault(judge.user_id, set()).add("judge")
    return result


@dataclass
class Reminder:
    user_id: int
    key: str
    title: str
    body: str
    roles: set
    path: str
    scheduled_at: datetime


def current_reminders(db, at=None):
    """At most one overdue stage per entity/family; expired families disappear."""
    at = utc(at or now())
    result = {}

    def add(family, identity, due, stages, audience, title, body, path, zone=REGION, cutoff=None, admissions=None):
        cutoff = cutoff or datetime.combine(due + timedelta(days=1), time(), zone)
        if at >= utc(cutoff):
            return
        passed = [(label, moment) for label, moment in stages if utc(moment) <= at]
        if not passed:
            return
        label, moment = max(passed, key=lambda pair: utc(pair[1]))
        key = f"tg-reminder:{family}:{identity}:{label}"
        for user_id, roles in audience.items():
            roles = roles & {"athlete"}
            if admissions is not None and "athlete" in roles:
                since = admissions.get(user_id)
                if since is None or utc(moment) < utc(since):
                    roles = roles - {"athlete"}
            user = db.get(User, user_id)
            if roles and user and utc(moment) >= utc(user.created_at):
                result[user_id, key] = Reminder(user_id, key, title, body, roles, path, moment)

    def daily(due, offsets, zone=REGION):
        return [(str(n), datetime.combine(due - timedelta(days=n), time(9), zone)) for n in offsets]

    for comp in db.scalars(select(Competition).where(Competition.state.in_(["open", "closed"]))):
        zone = ZoneInfo(comp.timezone)
        start = datetime.combine(comp.start_date, comp.start_time or time.max, zone)
        stages = daily(comp.start_date, [3, 0], zone)
        if comp.start_time:
            stages = [(label, moment) for label, moment in stages if moment < start]
            stages.append(("hour", start - timedelta(hours=1)))
        stamp = f"{comp.id}:{comp.start_date}:{comp.start_time}:{comp.timezone}"
        admissions = admitted_athletes(db, comp)
        add("start", stamp, comp.start_date, stages, competition_audience(db, comp),
            "Напоминание о соревновании", f"{comp.title}\nНачало: {comp.start_date:%d.%m.%Y} "
            f"{comp.start_time.strftime('%H:%M') if comp.start_time else '(время не указано)'} "
            f"({comp.timezone})\n{comp.location}", f"/competitions/{comp.id}", zone, start, admissions=admissions)
        if competition_in_progress(comp, at):
            add("end", f"{comp.id}:{comp.end_date}", comp.end_date,
                daily(comp.end_date, [1, 0], zone), {uid: {"athlete"} for uid in admissions},
                "Соревнование завершается", f"{comp.title}\nОкончание: {comp.end_date:%d.%m.%Y} ({comp.timezone})",
                f"/competitions/{comp.id}", zone, admissions=admissions)

    admin_users = admins(db)
    for rank in db.scalars(select(SportsRank)):
        athlete = db.get(Athlete, rank.athlete_id)
        audience = athlete_audience(db, rank.athlete_id, rank.discipline_id)
        add("rank", f"{rank.id}:{rank.expires_on}", rank.expires_on, daily(rank.expires_on, [30, 7, 1]),
            audience, "Истекает спортивный разряд", f"{athlete.user.full_name}: {rank.name}\nСрок: {rank.expires_on:%d.%m.%Y}", "/ranks")
    for category in db.scalars(select(JudgeCategory)):
        judge = db.get(Judge, category.judge_id)
        audience = {}
        if "judge" in roles_for(db, judge.user_id):
            audience.setdefault(judge.user_id, set()).add("judge")
        add("category", f"{category.id}:{category.expires_on}", category.expires_on,
            daily(category.expires_on, [30, 7, 1]), audience, "Истекает судейская категория",
            f"{judge.user.full_name}: {category.name}\nСрок: {category.expires_on:%d.%m.%Y}", "/ranks")
    for deadline in db.scalars(select(Deadline).where(Deadline.done.is_(False))):
        add("report", f"{deadline.id}:{deadline.due_on}", deadline.due_on,
            daily(deadline.due_on, [30, 7, 1]), admin_users, "Приближается срок отчёта",
            f"{deadline.title}: {deadline.due_on:%d.%m.%Y}", "/deadlines")
    today = at.astimezone(REGION).date()
    feb = date(today.year if (today.month, today.day) <= (2, 1) else today.year + 1, 2, 1)
    add("governor", str(feb.year), feb, daily(feb, [30, 7, 1]), admin_users,
        "Ходатайства на премии Губернатора", f"Срок подачи: {feb:%d.%m.%Y}", "/deadlines")
    return result


def schedule(db, at=None):
    current = current_reminders(db, at)
    for reminder in current.values():
        notify(db, [reminder.user_id], reminder.title, reminder.body, reminder.key)
        notice = db.scalar(select(Notification).where(
            Notification.user_id == reminder.user_id, Notification.event_key == reminder.key))
        notice.telegram_context = {"roles": sorted(reminder.roles), "path": reminder.path}
    db.flush()
    return current
