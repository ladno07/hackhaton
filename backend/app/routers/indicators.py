from datetime import date
from pathlib import PurePath
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import IndicatorIn
from app.security import Actor, allow
from app.services.common import *
from app.services.documents import OfficialDocument
from app.services.indicators import (
    document_info,
    entered_indicators,
    indicator_info,
    number,
    registry_indicators,
)
from app.routers.reports import HEAD, download

router = APIRouter(tags=["Показатели развития"])

DOCUMENT_MAX_SIZE = 10 * 1024 * 1024
DOCUMENTS_PER_INDICATOR = 10
OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
ZIP = (b"PK\x03\x04",)
DOCUMENT_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ZIP,
    ),
    ".doc": ("application/msword", OLE),
    ".odt": ("application/vnd.oasis.opendocument.text", ZIP),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ZIP,
    ),
    ".xls": ("application/vnd.ms-excel", OLE),
    ".ods": ("application/vnd.oasis.opendocument.spreadsheet", ZIP),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
}


def period(start_year, end_year):
    if not 0 <= end_year - start_year <= 30:
        raise HTTPException(422, "Укажите период не длиннее 31 года")


def fill(db, obj, data, actor):
    if data.organization_id:
        require(db, Organization, data.organization_id)
    for k, v in data.model_dump().items():
        setattr(obj, k, v)
    obj.updated_by = actor.user.id
    obj.updated_at = now()


@router.get("/indicators")
def indicators(
    start_year: int | None = Query(None, ge=1970, le=2100),
    end_year: int | None = Query(None, ge=1970, le=2100),
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    start_year = start_year or date.today().year - 2
    end_year = end_year or date.today().year
    period(start_year, end_year)
    return {
        "years": list(range(start_year, end_year + 1)),
        "registry": registry_indicators(db, start_year, end_year),
        "entered": entered_indicators(db, start_year, end_year),
    }


@router.post("/indicators", status_code=201)
def add_indicator(
    data: IndicatorIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = DevelopmentIndicator()
    fill(db, obj, data, actor)
    db.add(obj)
    audit(db, actor, "Добавление показателя развития", obj, {"name": obj.name, "year": obj.year})
    return indicator_info(db, obj)


@router.put("/indicators/{indicator_id}")
def edit_indicator(
    indicator_id: int,
    data: IndicatorIn,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, DevelopmentIndicator, indicator_id)
    before = {"value": obj.value, "source": obj.source}
    fill(db, obj, data, actor)
    audit(
        db,
        actor,
        "Изменение показателя развития",
        obj,
        {"before": before, "after": {"value": obj.value, "source": obj.source}},
    )
    return indicator_info(db, obj)


@router.delete("/indicators/{indicator_id}", status_code=204)
def delete_indicator(
    indicator_id: int,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, DevelopmentIndicator, indicator_id)
    audit(
        db,
        actor,
        "Удаление показателя развития",
        obj,
        {"name": obj.name, "year": obj.year, "documents": len(obj.documents)},
    )
    db.delete(obj)


@router.post("/indicators/{indicator_id}/documents", status_code=201)
async def upload_document(
    indicator_id: int,
    file: UploadFile = File(...),
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, DevelopmentIndicator, indicator_id)
    if len(obj.documents) >= DOCUMENTS_PER_INDICATOR:
        raise HTTPException(
            409, f"К показателю можно прикрепить не больше {DOCUMENTS_PER_INDICATOR} документов"
        )
    name = PurePath((file.filename or "").replace("\\", "/")).name.strip()
    ext = PurePath(name).suffix.lower()
    if ext not in DOCUMENT_TYPES:
        raise HTTPException(
            422, "Допустимые форматы: PDF, DOCX, DOC, ODT, XLSX, XLS, ODS, JPG, PNG"
        )
    content = await file.read(DOCUMENT_MAX_SIZE + 1)
    if not content:
        raise HTTPException(422, "Файл пустой")
    if len(content) > DOCUMENT_MAX_SIZE:
        raise HTTPException(413, "Размер документа не должен превышать 10 МБ")
    mime, signatures = DOCUMENT_TYPES[ext]
    if not content.startswith(signatures):
        raise HTTPException(422, "Содержимое файла не соответствует расширению")
    doc = IndicatorDocument(
        filename=name[-255:],
        content_type=mime,
        size=len(content),
        data=content,
        uploaded_by=actor.user.id,
    )
    obj.documents.append(doc)
    audit(
        db,
        actor,
        "Прикрепление документа к показателю",
        obj,
        {"filename": doc.filename, "size": doc.size},
    )
    return document_info(doc)


@router.get("/indicator-documents/{document_id}")
def download_document(
    document_id: int,
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    doc = require(db, IndicatorDocument, document_id)
    fallback = f"indicator-document-{doc.id}{PurePath(doc.filename).suffix}"
    return Response(
        doc.data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(doc.filename)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/indicator-documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    doc = require(db, IndicatorDocument, document_id)
    audit(
        db,
        actor,
        "Удаление документа показателя",
        db.get(DevelopmentIndicator, doc.indicator_id),
        {"filename": doc.filename},
    )
    db.delete(doc)


@router.get("/exports/indicators.{fmt}")
def export_indicators(
    fmt: str,
    start_year: int | None = Query(None, ge=1970, le=2100),
    end_year: int | None = Query(None, ge=1970, le=2100),
    actor: Actor = Depends(allow("admin", "ministry")),
    db: Session = Depends(get_db),
):
    start_year = start_year or date.today().year - 2
    end_year = end_year or date.today().year
    period(start_year, end_year)
    rows = []
    for r in registry_indicators(db, start_year, end_year):
        for v in r["values"]:
            rows.append(
                [
                    v["year"],
                    r["name"],
                    f"{number(v['value'])} {r['unit']}",
                    "Реестр платформы. " + r["source"],
                    "—",
                ]
            )
    for e in entered_indicators(db, start_year, end_year):
        name = e["name"] + (f" ({e['organization']})" if e["organization"] else "")
        rows.append(
            [
                e["year"],
                name,
                f"{number(e['value'])} {e['unit']}",
                e["source"] + (f". {e['comment']}" if e["comment"] else ""),
                "; ".join(d["filename"] for d in e["documents"]) or "не прикреплены",
            ]
        )
    rows.sort(key=lambda r: -r[0])
    return download(
        OfficialDocument(
            kind="Отчёт",
            title="о показателях развития спортивного программирования",
            headers=["Год", "Показатель", "Значение", "Источник", "Подтверждающие документы"],
            rows=rows,
            dated=date.today(),
            meta=[("Период", f"{start_year}–{end_year} гг.")],
            outro=[
                "Показатели реестра рассчитаны платформой автоматически; "
                "внесённые показатели приведены по указанным источникам."
            ],
            signatures=[HEAD, ("Исполнитель", actor.user.full_name)],
        ),
        fmt,
        "indicators",
    )
