"""Protocol rules: shared places, team entries and published versions."""

from fastapi import HTTPException
from sqlalchemy import func, select
from app.models import *

FIRST_VERSION_REASON = "Первичная публикация"


def check_entries(results, approved):
    """All approved athletes once; a team is one entry whose members share
    place and score; places follow the "1, 1, 3" rule over entries."""
    ids = [r.athlete_id for r in results]
    if set(ids) != set(approved) or len(set(ids)) != len(ids):
        raise HTTPException(
            422, "Нужны результаты всех одобренных участников, каждого по одному разу"
        )
    entries = {}
    for r in results:
        key = ("team", r.team_name) if r.team_name else ("athlete", r.athlete_id)
        if entries.setdefault(key, (r.place, r.score)) != (r.place, r.score):
            raise HTTPException(
                422, f"У участников команды «{r.team_name}» должны совпадать место и баллы"
            )
    places = sorted(place for place, _ in entries.values())
    for i, place in enumerate(places):
        if place != i + 1 and (i == 0 or place != places[i - 1]):
            raise HTTPException(
                422,
                "Места идут от 1; после N участников на одном месте следующее "
                "место пропускает N − 1 позиций (например, 1, 1, 3)",
            )


def current_results(db, comp_id):
    return db.scalars(
        select(CompetitionResult)
        .where(CompetitionResult.competition_id == comp_id)
        .order_by(
            CompetitionResult.place, CompetitionResult.team_name, CompetitionResult.id
        )
    ).all()


def snapshot(db, comp_id):
    entries = []
    for r in current_results(db, comp_id):
        athlete = db.get(Athlete, r.athlete_id)
        org = (
            db.get(Organization, athlete.organization_id)
            if athlete.organization_id
            else None
        )
        entries.append(
            {
                "result_id": r.id,
                "athlete_id": r.athlete_id,
                "full_name": athlete.user.full_name,
                "organization": org.name if org else "Без организации",
                "team_name": r.team_name,
                "place": r.place,
                "score": r.score,
            }
        )
    return entries


def add_version(db, comp, user_id, reason=FIRST_VERSION_REASON):
    db.flush()
    number = (
        db.scalar(
            select(func.max(ProtocolVersion.version)).where(
                ProtocolVersion.competition_id == comp.id
            )
        )
        or 0
    ) + 1
    obj = ProtocolVersion(
        competition_id=comp.id,
        version=number,
        created_by=user_id,
        reason=reason,
        entries=snapshot(db, comp.id),
    )
    db.add(obj)
    db.flush()
    return obj


def versions(db, comp_id):
    return db.scalars(
        select(ProtocolVersion)
        .where(ProtocolVersion.competition_id == comp_id)
        .order_by(ProtocolVersion.version)
    ).all()


def changes(old, new):
    before = {e["athlete_id"]: e for e in old}
    output = []
    for e in new:
        b = before.get(e["athlete_id"])
        if b and any(b[k] != e[k] for k in ("place", "score", "team_name")):
            output.append(
                {
                    "result_id": e["result_id"],
                    "full_name": e["full_name"],
                    **{f"old_{k}": b[k] for k in ("place", "score", "team_name")},
                    **{k: e[k] for k in ("place", "score", "team_name")},
                }
            )
    return output


def rank_warnings(db, result_ids):
    """Ranks and pending rank applications based on the changed results."""
    if not result_ids:
        return []
    ranks = db.scalars(select(SportsRank).where(SportsRank.result_id.in_(result_ids)))
    pending = db.scalars(
        select(RankApplication).where(
            RankApplication.result_id.in_(result_ids),
            RankApplication.status == "pending",
        )
    )
    return [
        f"{db.get(Athlete, r.athlete_id).user.full_name}: присвоен разряд «{r.name}»"
        for r in ranks
    ] + [
        f"{db.get(Athlete, a.athlete_id).user.full_name}: заявка на разряд «{a.name}» на рассмотрении"
        for a in pending
    ]


def version_history(db, comp_id):
    """Newest first, with changes against the previous version."""
    items, previous = [], None
    for v in versions(db, comp_id):
        diff = changes(previous.entries, v.entries) if previous else []
        author = db.get(User, v.created_by) if v.created_by else None
        items.append(
            {
                "version": v.version,
                "created_at": v.created_at,
                "author": author.full_name if author else None,
                "reason": v.reason,
                "changes": diff,
                "rank_warnings": rank_warnings(db, [c["result_id"] for c in diff]),
            }
        )
        previous = v
    return items[::-1]
