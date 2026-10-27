"""Profile-based recipients for competition announcements and registration deadlines."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models import Athlete, AthleteDiscipline, CompetitionApplication, UserRole, now
from app.services.age_groups import age_check


def eligible(db, athlete, comp, at):
    enrollment = db.get(AthleteDiscipline, (athlete.id, comp.discipline_id))
    return bool(enrollment and enrollment.start_year <= comp.start_date.year
                and (enrollment.end_year is None or enrollment.end_year >= comp.start_date.year)
                and (athlete.suspended_until is None or athlete.suspended_until < at.date())
                and age_check(db, comp, athlete)["eligible"])


def registration_recipients(db, comp, at=None, exclude_applied=False):
    at = at or now()
    zone = ZoneInfo(comp.timezone)
    local = at.astimezone(zone)
    if comp.state != "open" or local.date() > comp.deadline:
        return []
    applicants = set(db.scalars(select(CompetitionApplication.athlete_id).where(
        CompetitionApplication.competition_id == comp.id))) if exclude_applied else set()
    return [athlete.user_id for athlete in db.scalars(select(Athlete).join(
        UserRole, UserRole.user_id == Athlete.user_id).where(UserRole.role_id == "athlete"))
        if athlete.id not in applicants and eligible(db, athlete, comp, local)]


def reminder_stage(due, offsets, at=None, timezone="Asia/Yekaterinburg"):
    """Latest due reminder; its event time prevents history being sent to new accounts."""
    at = at or now()
    zone = ZoneInfo(timezone)
    stages = [(days, datetime.combine(due - timedelta(days=days), time(9), zone))
              for days in offsets]
    passed = [(days, moment) for days, moment in stages if moment <= at]
    return max(passed, key=lambda stage: stage[1]) if passed else None


def admitted_athletes(db, comp):
    return {athlete.user_id: application.approved_at or application.created_at
            for application, athlete in db.execute(select(CompetitionApplication, Athlete).join(
                Athlete, Athlete.id == CompetitionApplication.athlete_id).join(
                UserRole, UserRole.user_id == Athlete.user_id).where(
                CompetitionApplication.competition_id == comp.id,
                CompetitionApplication.status == "approved", UserRole.role_id == "athlete"))}


def competition_in_progress(comp, at=None):
    local = (at or now()).astimezone(ZoneInfo(comp.timezone))
    return (comp.state in ("open", "closed")
            and datetime.combine(comp.start_date, comp.start_time or time(), local.tzinfo) <= local
            and local.date() <= comp.end_date)
