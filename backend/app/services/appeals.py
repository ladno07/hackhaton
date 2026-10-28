"""Appeals against protocols and violations: deadlines, scope and views."""

from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.models import *
from app.services.common import can_athlete, own, visible_athletes

# A protocol version may be appealed for 3 days after it is published, so a
# correction reopens the window; a violation decision — for 10 days.
RESULT_APPEAL_DAYS = 3
VIOLATION_APPEAL_DAYS = 10
# the federation is expected to decide within 5 days of submission
DECISION_DAYS = 5

KINDS = {
    "rules": "Нарушение правил соревнований",
    "conduct": "Неспортивное поведение",
    "doping": "Нарушение антидопинговых правил",
    "other": "Иное нарушение",
}
SANCTIONS = {"warning": "Предупреждение", "suspension": "Отстранение"}
STATUSES = {
    "pending": "На рассмотрении",
    "upheld": "Удовлетворена",
    "rejected": "Отклонена",
    "withdrawn": "Отозвана",
}


def latest_version(db, comp_id):
    return db.scalar(
        select(ProtocolVersion)
        .where(ProtocolVersion.competition_id == comp_id)
        .order_by(ProtocolVersion.version.desc())
    )


def result_deadline(db, comp_id):
    version = latest_version(db, comp_id)
    return version.created_at.date() + timedelta(days=RESULT_APPEAL_DAYS) if version else None


def violation_deadline(violation):
    return violation.created_at.date() + timedelta(days=VIOLATION_APPEAL_DAYS)


def can_follow(db, actor, athlete_id, discipline_id=None):
    try:
        can_athlete(db, actor, athlete_id, discipline_id)
        return True
    except HTTPException:
        return False


def judged_competitions(db, actor):
    judge = own(db, Judge, actor)
    return set(
        db.scalars(
            select(CompetitionJudge.competition_id).where(
                CompetitionJudge.judge_id == judge.id
            )
        )
    )


def appeal_scope(db, actor, query):
    """Federation and ministry see all; athlete and coach — their athletes;
    a judge — result appeals of competitions where they work in the panel."""
    if actor.role in ("admin", "ministry"):
        return query
    if actor.role == "judge":
        return query.where(Appeal.competition_id.in_(judged_competitions(db, actor)))
    return query.where(Appeal.athlete_id.in_(visible_athletes(db, actor)))


def check_access(db, actor, appeal):
    if not db.scalar(appeal_scope(db, actor, select(Appeal.id).where(Appeal.id == appeal.id))):
        raise HTTPException(404, "Апелляция не найдена")


def violation_text(v):
    sanction = SANCTIONS[v.sanction]
    if v.suspended_until:
        sanction += f" до {v.suspended_until:%d.%m.%Y}"
    return f"{KINDS[v.kind]} от {v.occurred_on:%d.%m.%Y}: {sanction}"


def violation_view(db, v):
    athlete = db.get(Athlete, v.athlete_id)
    comp = db.get(Competition, v.competition_id) if v.competition_id else None
    pending = db.scalar(
        select(Appeal.id).where(Appeal.violation_id == v.id, Appeal.status == "pending")
    )
    deadline = violation_deadline(v)
    return {
        **{
            k: getattr(v, k)
            for k in (
                "id", "athlete_id", "competition_id", "kind", "occurred_on",
                "description", "sanction", "suspended_until", "status",
                "cancel_reason", "cancelled_at", "created_at",
            )
        },
        "full_name": athlete.user.full_name,
        "competition": comp.title if comp else None,
        "kind_name": KINDS[v.kind],
        "sanction_name": SANCTIONS[v.sanction],
        "summary": violation_text(v),
        "appeal_until": deadline,
        "can_appeal": v.status == "active" and deadline >= date.today() and not pending,
    }


def appeal_view(db, actor, a):
    athlete = db.get(Athlete, a.athlete_id)
    comp = db.get(Competition, a.competition_id) if a.competition_id else None
    result = db.get(CompetitionResult, a.result_id) if a.result_id else None
    violation = db.get(Violation, a.violation_id) if a.violation_id else None
    submitter = db.get(User, a.submitted_by)
    decider = db.get(User, a.decided_by) if a.decided_by else None
    entry = None
    if a.protocol_version and comp:
        version = db.scalar(
            select(ProtocolVersion).where(
                ProtocolVersion.competition_id == comp.id,
                ProtocolVersion.version == a.protocol_version,
            )
        )
        entry = next(
            (e for e in version.entries if e["athlete_id"] == a.athlete_id), None
        ) if version else None
    if a.subject == "result":
        subject = f"Протокол «{comp.title}», редакция {a.protocol_version}"
        if entry:
            subject += f": {entry['place']} место, {entry['score']:g} б."
    else:
        subject = "Решение о нарушении: " + violation_text(violation)
    owner_side = actor.role in ("athlete", "coach")
    return {
        **{
            k: getattr(a, k)
            for k in (
                "id", "athlete_id", "subject", "competition_id", "result_id",
                "protocol_version", "violation_id", "reason", "request", "status",
                "decision", "decided_at", "resolution_version", "created_at",
                "submitted_role",
            )
        },
        "number": f"А-{a.id}",
        "full_name": athlete.user.full_name,
        "competition": comp.title if comp else None,
        "subject_text": subject,
        "current_place": result.place if result else None,
        "current_score": result.score if result else None,
        "status_name": STATUSES[a.status],
        "submitted_by_name": submitter.full_name,
        "decided_by_name": decider.full_name if decider else None,
        "can_withdraw": owner_side and a.status == "pending",
        "can_decide": actor.role == "admin" and a.status == "pending",
    }


def appeal_options(db, actor):
    """What the athlete/coach may appeal now: lines of published protocols
    within the window and active violations within the window."""
    athletes = visible_athletes(db, actor)
    pending = select(Appeal).where(Appeal.status == "pending")
    busy_results = {a.result_id for a in db.scalars(pending) if a.result_id}
    busy_violations = {a.violation_id for a in db.scalars(pending) if a.violation_id}
    results = []
    for r, comp in db.execute(
        select(CompetitionResult, Competition)
        .join(Competition, Competition.id == CompetitionResult.competition_id)
        .where(
            Competition.state == "published",
            CompetitionResult.athlete_id.in_(athletes),
        )
        .order_by(Competition.end_date.desc())
    ):
        deadline = result_deadline(db, comp.id)
        if (
            not deadline
            or deadline < date.today()
            or r.id in busy_results
            or not can_follow(db, actor, r.athlete_id, comp.discipline_id)
        ):
            continue
        results.append(
            {
                "result_id": r.id,
                "athlete_id": r.athlete_id,
                "full_name": db.get(Athlete, r.athlete_id).user.full_name,
                "competition": comp.title,
                "place": r.place,
                "score": r.score,
                "protocol_version": latest_version(db, comp.id).version,
                "appeal_until": deadline,
            }
        )
    violations = [
        violation_view(db, v)
        for v in db.scalars(
            select(Violation).where(
                Violation.athlete_id.in_(athletes), Violation.status == "active"
            )
        )
        if v.id not in busy_violations and violation_deadline(v) >= date.today()
    ]
    return {
        "results": results,
        "violations": violations,
        "result_days": RESULT_APPEAL_DAYS,
        "violation_days": VIOLATION_APPEAL_DAYS,
    }


def restore_suspension(db, athlete, cancelled):
    """After cancelling a suspension: keep the latest remaining one; leave a
    manual suspension (set in the registry) untouched."""
    if athlete.suspended_until != cancelled.suspended_until:
        return
    remaining = db.scalars(
        select(Violation)
        .where(
            Violation.athlete_id == athlete.id,
            Violation.status == "active",
            Violation.sanction == "suspension",
            Violation.id != cancelled.id,
        )
        .order_by(Violation.suspended_until.desc())
    ).first()
    athlete.suspended_until = remaining.suspended_until if remaining else None
    athlete.suspension_reason = remaining.description if remaining else None
