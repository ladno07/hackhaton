"""Public DTOs are explicit allowlists. Publication never grants account access."""

import hashlib
import hmac
import json
import re
import secrets
from datetime import date, timezone
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import *
from app.config import settings
from app.services.common import age_at
from app.services.athlete_ids import public_athlete_id

CONSENT_VERSION = "passport-2026-01"


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def iso(value):
    if value is None:
        return None
    if not value.tzinfo:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def new_slug():
    return "p-" + secrets.token_urlsafe(24)


def public_url(path):
    return settings.public_base_url + path


def guardian_ok(db, athlete):
    if age_at(athlete.user.birth_date) >= 18:
        return True
    consent = db.get(PassportGuardianConsent, athlete.id)
    return bool(
        consent
        and consent.status == "approved"
        and consent.guardian_name == athlete.user.guardian_name
    )


def is_available(db, cfg, athlete):
    return bool(
        cfg
        and cfg.enabled
        and cfg.slug
        and cfg.consent_at
        and guardian_ok(db, athlete)
        and any(r.id == "athlete" for r in athlete.user.roles)
        and not (athlete.suspended_until and athlete.suspended_until >= date.today())
    )


def publication(db, slug):
    cfg = (
        db.scalar(select(PassportPublication).where(PassportPublication.slug == slug))
        if re.fullmatch(r"p-[A-Za-z0-9_-]{32}", slug)
        else None
    )
    athlete = db.get(Athlete, cfg.athlete_id) if cfg else None
    if not athlete or not is_available(db, cfg, athlete):
        raise HTTPException(404, "Паспорт не опубликован или временно недоступен")
    return cfg, athlete


def ratings(db, athlete_id):
    season = date.today().year
    all_rows = db.execute(
        select(Rating, Athlete)
        .join(Athlete, Athlete.id == Rating.athlete_id)
        .where(Rating.season == season)
        .order_by(Rating.points.desc(), Rating.athlete_id)
    ).all()
    positions, output = {}, []
    for rating, athlete in all_rows:
        if athlete.suspended_until and athlete.suspended_until >= date.today():
            continue
        positions[rating.discipline_id] = positions.get(rating.discipline_id, 0) + 1
        if rating.athlete_id == athlete_id:
            output.append(
                {
                    "discipline": db.get(Discipline, rating.discipline_id).short_name,
                    "points": rating.points,
                    "position": positions[rating.discipline_id],
                    "season": season,
                }
            )
    return output


VISIBILITY_DEFAULTS = {
    "show_results": True,
    "show_rating": True,
    "show_ranks": True,
    "show_disciplines": True,
    "show_organization": True,
    "show_municipality": True,
    "show_team": True,
    "show_rusada": False,
    "show_training_stage": False,
    "show_training_years": False,
}


def visibility_data(cfg):
    return {
        key: getattr(cfg, key) if cfg else default
        for key, default in VISIBILITY_DEFAULTS.items()
    }


def athlete_profile_data(db, athlete, cfg):
    visible = visibility_data(cfg)
    rows = (
        db.execute(
            select(CompetitionResult, Competition)
            .join(Competition, Competition.id == CompetitionResult.competition_id)
            .where(
                CompetitionResult.athlete_id == athlete.id,
                Competition.state == "published",
            )
            .order_by(Competition.start_date.desc(), Competition.id.desc())
        ).all()
        if visible["show_results"]
        else []
    )
    history = [
        {
            "title": comp.title,
            "date": comp.start_date.isoformat(),
            "discipline": db.get(Discipline, comp.discipline_id).short_name,
            "place": result.place,
            "score": result.score,
            "team_name": result.team_name,
        }
        for result, comp in rows
    ]
    org = (
        db.get(Organization, athlete.organization_id)
        if visible["show_organization"] and athlete.organization_id
        else None
    )
    discipline_rows = (
        db.scalars(
            select(AthleteDiscipline)
            .where(AthleteDiscipline.athlete_id == athlete.id)
            .order_by(AthleteDiscipline.discipline_id)
        ).all()
        if visible["show_disciplines"]
        else []
    )
    return {
        "full_name": athlete.user.full_name,
        "public_id": public_athlete_id(athlete.id),
        "organization": (org.name if org else "Без организации")
        if visible["show_organization"]
        else None,
        "municipality": athlete.municipality if visible["show_municipality"] else None,
        "training_stage": athlete.training_stage
        if visible["show_training_stage"]
        else None,
        "disciplines": [
            {
                "name": db.get(Discipline, d.discipline_id).short_name,
                **(
                    {"start_year": d.start_year, "end_year": d.end_year}
                    if visible["show_training_years"]
                    else {}
                ),
            }
            for d in discipline_rows
        ],
        "ranks": [
            {
                "name": r.name,
                "discipline": db.get(Discipline, r.discipline_id).short_name,
                "expires_on": r.expires_on.isoformat(),
                "active": r.expires_on >= date.today(),
            }
            for r in db.scalars(
                select(SportsRank)
                .where(SportsRank.athlete_id == athlete.id)
                .order_by(SportsRank.assigned_on.desc())
            )
        ]
        if visible["show_ranks"]
        else [],
        "ratings": ratings(db, athlete.id) if visible["show_rating"] else [],
        "team": [
            {
                "discipline": db.get(Discipline, t.discipline_id).short_name,
                "season": t.season,
            }
            for t in db.scalars(
                select(TeamMember).where(
                    TeamMember.athlete_id == athlete.id,
                    TeamMember.season == date.today().year,
                )
            )
        ]
        if visible["show_team"]
        else [],
        "rusada": {"completed_on": athlete.rusada_date.isoformat()}
        if visible["show_rusada"] and athlete.rusada_date
        else None,
        "results": history,
        "visibility": visible,
        "season": date.today().year,
        "stats": {
            "competitions": len(rows) if visible["show_results"] else None,
            "wins": sum(r.place == 1 for r, _ in rows)
            if visible["show_results"]
            else None,
            "podiums": sum(r.place <= 3 for r, _ in rows)
            if visible["show_results"]
            else None,
        },
    }


def private_certificate_data(db, actor, result_id, version_number=None):
    from app.services.common import require, can_athlete

    result = require(db, CompetitionResult, result_id)
    comp = require(db, Competition, result.competition_id)
    can_athlete(db, actor, result.athlete_id, comp.discipline_id)
    if comp.state != "published":
        raise HTTPException(
            409, "Справка доступна только по опубликованным результатам"
        )
    versions = db.scalars(
        select(ProtocolVersion)
        .where(ProtocolVersion.competition_id == comp.id)
        .order_by(ProtocolVersion.version.desc())
    ).all()
    version = (
        next((v for v in versions if v.version == version_number), None)
        if version_number is not None
        else (versions[0] if versions else None)
    )
    if not version:
        raise HTTPException(404, "Опубликованная редакция протокола не найдена")
    entry = next(
        (e for e in version.entries if e["athlete_id"] == result.athlete_id), None
    )
    if not entry:
        raise HTTPException(409, "Участник отсутствует в выбранной редакции протокола")
    payload = {
        "public_id": public_athlete_id(result.athlete_id),
        "competition": {
            "title": comp.title,
            "start_date": comp.start_date.isoformat(),
            "end_date": comp.end_date.isoformat(),
            "discipline": db.get(Discipline, comp.discipline_id).short_name,
            "location": comp.location,
            "calendar_plan": comp.calendar_plan,
            "calendar_number": comp.calendar_number,
        },
        "entry": {
            k: entry.get(k)
            for k in ["full_name", "organization", "team_name", "place", "score"]
        },
        "version": version.version,
        "published_at": iso(version.created_at),
    }
    return {
        **payload,
        "fingerprint": fingerprint(payload),
        "result_id": result.id,
        "certificate_number": f"FSP-CERT-{result.id}-V{version.version}",
        "latest_version": versions[0].version,
        "is_current": versions[0].version == version.version,
        "path": f"/certificates/{result.id}?version={version.version}",
        "verification_path": "/check-certificate/"
        + certificate_check_token(version.id, result.id),
        "access_note": "Справка доступна только после входа: спортсмену, его действующему тренеру по дисциплине и федерации.",
    }


# These tokens only authorize a minimal verification record, never the PDF/profile.
def certificate_check_token(protocol_id, result_id):
    payload = f"{protocol_id}.{result_id}"
    signature = hmac.new(
        settings.jwt_secret.encode(),
        ("certificate-check-v1:" + payload).encode(),
        hashlib.sha256,
    ).hexdigest()
    return payload + "." + signature


def public_certificate_check(db, check_token):
    match = re.fullmatch(
        r"([1-9][0-9]{0,17})\.([1-9][0-9]{0,17})\.([a-f0-9]{64})", check_token
    )
    if not match:
        raise HTTPException(404, "Справка не найдена")
    protocol_id, result_id = int(match[1]), int(match[2])
    if not hmac.compare_digest(
        check_token, certificate_check_token(protocol_id, result_id)
    ):
        raise HTTPException(404, "Справка не найдена")
    protocol = db.get(ProtocolVersion, protocol_id)
    if not protocol:
        raise HTTPException(404, "Справка не найдена")
    entry = next((e for e in protocol.entries if e.get("result_id") == result_id), None)
    if not entry:
        raise HTTPException(404, "Справка не найдена")
    comp = db.get(Competition, protocol.competition_id)
    result = db.get(CompetitionResult, result_id)
    valid = bool(
        comp
        and comp.state == "published"
        and result
        and result.competition_id == protocol.competition_id
        and result.athlete_id == entry.get("athlete_id")
    )
    latest = db.scalar(
        select(func.max(ProtocolVersion.version)).where(
            ProtocolVersion.competition_id == protocol.competition_id
        )
    )
    # Explicit allowlist: do not return entries, people, result IDs, PDF paths or hashes.
    return {
        "certificate_number": f"FSP-CERT-{result_id}-V{protocol.version}",
        "status": ("confirmed" if latest == protocol.version else "replaced")
        if valid
        else "invalid",
        "competition_title": comp.title if valid else None,
        "version": protocol.version,
        "published_at": iso(protocol.created_at) if valid else None,
    }
