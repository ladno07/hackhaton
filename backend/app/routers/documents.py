from fastapi import APIRouter, Depends, Response
from app.security import Actor, current_actor
from app.services.consents import consent_records, consent_record, consent_pdf

router = APIRouter(prefix="/my/documents", tags=["Мои документы"])
HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
}


@router.get("")
def my_documents(response: Response, actor: Actor = Depends(current_actor)):
    response.headers.update(HEADERS)
    return consent_records(actor.user)


@router.get("/{kind}.pdf")
def download_consent(kind: str, actor: Actor = Depends(current_actor)):
    # No user ID is accepted: even administrators download only their own consent.
    record = consent_record(actor.user, kind)
    return Response(
        consent_pdf(record),
        media_type="application/pdf",
        headers={**HEADERS, "Content-Disposition": f'attachment; filename="consent-{record["id"]}.pdf"'},
    )


@router.get("/{kind}")
def view_consent(kind: str, response: Response, actor: Actor = Depends(current_actor)):
    response.headers.update(HEADERS)
    return consent_record(actor.user, kind)
