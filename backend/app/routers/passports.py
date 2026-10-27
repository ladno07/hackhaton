"""Authenticated athlete profiles and private participation certificates."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Athlete, PassportPublication, CompetitionResult, now
from app.schemas import ProfileVisibilityIn
from app.security import Actor, allow, current_actor
from app.services.common import own, require, audit
from app.services.passports import (
    visibility_data,
    athlete_profile_data,
    private_certificate_data,
    public_url,
    public_certificate_check,
)
from app.services.passport_pdf import pdf_document

router = APIRouter(tags=["Профили и справки"])
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
}


@router.get("/my/profile-visibility")
def my_visibility(
    actor: Actor = Depends(allow("athlete")), db: Session = Depends(get_db)
):
    athlete = own(db, Athlete, actor)
    return visibility_data(db.get(PassportPublication, athlete.id))


@router.put("/my/profile-visibility")
def set_visibility(
    data: ProfileVisibilityIn,
    actor: Actor = Depends(allow("athlete")),
    db: Session = Depends(get_db),
):
    athlete = own(db, Athlete, actor)
    db.execute(
        select(Athlete.id).where(Athlete.id == athlete.id).with_for_update(of=Athlete)
    ).all()
    cfg = db.get(PassportPublication, athlete.id)
    if not cfg:
        cfg = PassportPublication(athlete_id=athlete.id)
        db.add(cfg)
    for key, value in data.model_dump().items():
        setattr(cfg, key, value)
    cfg.enabled, cfg.slug, cfg.updated_at = False, None, now()
    audit(db, actor, "Настройки видимости профиля", athlete, data.model_dump())
    return visibility_data(cfg)


@router.get("/athlete-profiles/{athlete_id}")
def athlete_profile(
    athlete_id: int,
    actor: Actor = Depends(current_actor),
    db: Session = Depends(get_db),
):
    athlete = require(db, Athlete, athlete_id)
    return athlete_profile_data(db, athlete, db.get(PassportPublication, athlete.id))


@router.get("/results/{result_id}/certificate")
def certificate_details(
    result_id: int,
    version: int | None = Query(None, ge=1),
    actor: Actor = Depends(allow("athlete", "coach", "admin")),
    db: Session = Depends(get_db),
):
    return private_certificate_data(db, actor, result_id, version)


@router.get("/results/{result_id}/certificate.pdf")
def certificate_download(
    result_id: int,
    version: int | None = Query(None, ge=1),
    actor: Actor = Depends(allow("athlete", "coach", "admin")),
    db: Session = Depends(get_db),
):
    data = private_certificate_data(db, actor, result_id, version)
    audit(
        db,
        actor,
        "Скачивание справки об участии",
        require(db, CompetitionResult, result_id),
        {"version": data["version"]},
    )
    return Response(
        pdf_document(
            data,
            public_url(data["verification_path"]),
            certificate=True,
            private_access=True,
        ),
        media_type="application/pdf",
        headers={
            **HEADERS,
            "Content-Disposition": f'attachment; filename="certificate-{result_id}-v{data["version"]}.pdf"',
        },
    )


@router.api_route(
    "/public/passports/{legacy_path:path}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
@router.api_route(
    "/public/protocols/{legacy_path:path}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def public_access_closed(legacy_path: str):
    raise HTTPException(
        404, "Публичный доступ закрыт. Профили и справки доступны только после входа"
    )


@router.api_route(
    "/my/passport/{legacy_path:path}",
    methods=["GET", "POST", "PUT"],
    include_in_schema=False,
)
def old_publication_settings_closed(legacy_path: str):
    raise HTTPException(
        410, "Публичная публикация отключена. Используйте настройки видимости профиля"
    )


@router.api_route(
    "/my/passport", methods=["GET", "POST", "PUT"], include_in_schema=False
)
def old_publication_root_closed():
    raise HTTPException(
        410, "Публичная публикация отключена. Используйте настройки видимости профиля"
    )


@router.get("/public/certificates/{check_token}")
def check_certificate(
    check_token: str, response: Response, db: Session = Depends(get_db)
):
    response.headers.update(HEADERS)
    response.headers["Referrer-Policy"] = "no-referrer"
    return public_certificate_check(db, check_token)
