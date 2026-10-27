"""Stable public athlete identifiers. These identify a card, not grant access."""

import re
from fastapi import HTTPException
from app.models import Organization


def public_athlete_id(athlete_id):
    return f"FSP-{athlete_id:06d}"


def parse_athlete_id(value):
    normalized = value.strip().upper()
    match = re.fullmatch(r"FSP-([0-9]{6,10})", normalized)
    if match:
        number = int(match.group(1))
        if 0 < number <= 2147483647 and public_athlete_id(number) == normalized:
            return number
    raise HTTPException(422, "Укажите ID спортсмена в формате FSP-000123")


def candidate_view(db, athlete):
    org = (
        db.get(Organization, athlete.organization_id)
        if athlete.organization_id
        else None
    )
    return {
        "id": athlete.id,
        "public_id": public_athlete_id(athlete.id),
        "full_name": athlete.user.full_name,
        "organization": org.name if org else "Без организации",
        "municipality": athlete.municipality,
    }
