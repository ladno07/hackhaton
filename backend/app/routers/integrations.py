from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import *
from app.schemas import ApiTokenIn, ResultsImportIn, WebhookIn, WebhookPatch
from app.security import Actor, allow
from app.services.common import audit, require
from app.services.competition_teams import expand_results
from app.services.protocols import check_entries, current_results, versions
from app.services.integrations import (
    EVENTS,
    MAX_IMPORT_SIZE,
    SCOPES,
    ApiClient,
    api_client,
    application_data,
    competition_data,
    delivery_view,
    emit,
    issue_token,
    new_secret,
    parse_csv,
    preview,
    protocol_data,
    to_results,
    token_view,
)
from app.routers.competitions import apply_correction, locked, publish_results

router = APIRouter(tags=["Интеграции"])
api = APIRouter(prefix="/v1", tags=["API для внешних систем"])


# --- management (federation) ------------------------------------------------


@router.get("/integrations/meta")
def meta(actor: Actor = Depends(allow("admin"))):
    return {
        "scopes": [{"id": k, "name": v} for k, v in SCOPES.items()],
        "events": [{"id": k, "name": v} for k, v in EVENTS.items()],
    }


@router.get("/integrations/tokens")
def tokens(actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    items = db.scalars(select(ApiToken).order_by(ApiToken.id.desc())).all()
    return [token_view(db, t) for t in items]


@router.post("/integrations/tokens", status_code=201)
def create_token(
    data: ApiTokenIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    value, prefix, digest = issue_token()
    obj = ApiToken(
        name=data.name,
        prefix=prefix,
        token_hash=digest,
        scopes=data.scopes,
        expires_on=data.expires_on,
        created_by=actor.user.id,
    )
    db.add(obj)
    audit(db, actor, "Выпуск токена интеграции", obj, {"name": data.name, "scopes": data.scopes})
    # the plain value is shown once and never stored
    return {**token_view(db, obj), "token": value}


@router.delete("/integrations/tokens/{token_id}")
def revoke_token(
    token_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = require(db, ApiToken, token_id)
    if obj.revoked_at:
        raise HTTPException(409, "Токен уже отозван")
    obj.revoked_at = now()
    audit(db, actor, "Отзыв токена интеграции", obj, {"name": obj.name})
    return token_view(db, obj)


def webhook_view(db, obj, secret=False):
    last = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == obj.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(1)
    ).first()
    counts = {
        status: len(
            db.scalars(
                select(WebhookDelivery.id).where(
                    WebhookDelivery.webhook_id == obj.id, WebhookDelivery.status == status
                )
            ).all()
        )
        for status in ("pending", "delivered", "failed")
    }
    return {
        "id": obj.id,
        "name": obj.name,
        "url": obj.url,
        "events": obj.events,
        "active": obj.active,
        "created_at": obj.created_at,
        "deliveries": counts,
        "last_delivery": delivery_view(last) if last else None,
        **({"secret": obj.secret} if secret else {}),
    }


@router.get("/integrations/webhooks")
def webhooks(actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)):
    items = db.scalars(select(Webhook).order_by(Webhook.id)).all()
    return [webhook_view(db, w) for w in items]


@router.post("/integrations/webhooks", status_code=201)
def create_webhook(
    data: WebhookIn, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = Webhook(
        name=data.name,
        url=str(data.url),
        events=data.events,
        secret=new_secret(),
        created_by=actor.user.id,
    )
    db.add(obj)
    audit(db, actor, "Добавление вебхука", obj, {"url": obj.url, "events": obj.events})
    return webhook_view(db, obj, secret=True)


@router.patch("/integrations/webhooks/{hook_id}")
def edit_webhook(
    hook_id: int,
    data: WebhookPatch,
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    obj = require(db, Webhook, hook_id)
    changes = data.model_dump(exclude_none=True, mode="json")
    for key, value in changes.items():
        setattr(obj, key, value)
    audit(db, actor, "Изменение вебхука", obj, changes)
    return webhook_view(db, obj)


@router.post("/integrations/webhooks/{hook_id}/secret")
def rotate_secret(
    hook_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = require(db, Webhook, hook_id)
    obj.secret = new_secret()
    audit(db, actor, "Смена секрета вебхука", obj)
    return webhook_view(db, obj, secret=True)


@router.delete("/integrations/webhooks/{hook_id}", status_code=204)
def delete_webhook(
    hook_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = require(db, Webhook, hook_id)
    audit(db, actor, "Удаление вебхука", obj, {"url": obj.url})
    db.query(WebhookDelivery).filter(WebhookDelivery.webhook_id == obj.id).delete()
    db.delete(obj)


@router.post("/integrations/webhooks/{hook_id}/test", status_code=202)
def test_webhook(
    hook_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    """Queues a ping; the worker sends it within a minute."""
    obj = require(db, Webhook, hook_id)
    if not obj.active:
        raise HTTPException(409, "Включите вебхук перед проверкой")
    emit(
        db,
        "ping",
        f"ping:{now().isoformat()}",
        {"webhook": obj.name, "message": "Проверка вебхука ОренКод"},
        hooks=[obj],
    )
    return webhook_view(db, obj)


@router.get("/integrations/webhooks/{hook_id}/deliveries")
def deliveries(
    hook_id: int,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    require(db, Webhook, hook_id)
    items = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == hook_id)
        .order_by(WebhookDelivery.id.desc())
        .limit(limit)
    ).all()
    return [delivery_view(d) for d in items]


@router.post("/integrations/deliveries/{delivery_id}/retry")
def retry(
    delivery_id: int, actor: Actor = Depends(allow("admin")), db: Session = Depends(get_db)
):
    obj = require(db, WebhookDelivery, delivery_id)
    if obj.status == "delivered":
        raise HTTPException(409, "Событие уже доставлено")
    obj.status, obj.attempts, obj.next_attempt_at = "pending", 0, now()
    audit(db, actor, "Повторная отправка вебхука", obj, {"event": obj.event})
    return delivery_view(obj)


# --- import of results ------------------------------------------------------


def import_results(db, actor, comp, rows, reason, dry_run):
    """Publishes the first protocol or, when it is published, a corrected
    version with the given reason. A dry run only validates and previews."""
    data = to_results(db, comp, rows)
    if comp.state == "published":
        if not reason:
            raise HTTPException(
                422, "Протокол уже опубликован: укажите основание для новой редакции"
            )
        roster = {r.athlete_id: r for r in current_results(db, comp.id)}
    else:
        if comp.state != "closed":
            raise HTTPException(409, "Закройте приём заявок перед импортом результатов")
        if comp.end_date > date.today():
            raise HTTPException(422, "Соревнование ещё не завершено")
        roster = set(
            db.scalars(
                select(CompetitionApplication.athlete_id).where(
                    CompetitionApplication.competition_id == comp.id,
                    CompetitionApplication.status == "approved",
                )
            )
        )
    entries = expand_results(db, comp, data)
    check_entries(entries, roster)
    mode = "correction" if comp.state == "published" else "publication"
    summary = {"mode": mode, "count": len(entries), "rows": preview(db, comp, entries)}
    if dry_run:
        return {**summary, "dry_run": True}
    result = (
        apply_correction(db, actor, comp, data, reason)
        if mode == "correction"
        else publish_results(db, actor, comp, data)
    )
    return {**summary, **result, "dry_run": False}


@router.post("/competitions/{comp_id}/results/import")
async def import_file(
    comp_id: int,
    file: UploadFile = File(...),
    dry_run: bool = Form(True),
    reason: str | None = Form(None, min_length=5, max_length=2000),
    actor: Actor = Depends(allow("admin")),
    db: Session = Depends(get_db),
):
    raw = await file.read(MAX_IMPORT_SIZE + 1)
    rows = parse_csv(raw)
    comp = locked(db, comp_id)
    result = import_results(db, actor, comp, rows, reason, dry_run)
    if not dry_run:
        audit(db, actor, "Импорт результатов из файла", comp,
              {"file": file.filename, "count": result["count"], "mode": result["mode"]})
    return result


# --- API for external systems -----------------------------------------------


def visible_competition(db, comp_id):
    comp = db.get(Competition, comp_id)
    if not comp or comp.state == "draft":
        raise HTTPException(404, "Соревнование не найдено")
    return comp


@api.get("/me", summary="Сведения о токене")
def whoami(client: ApiClient = Depends(api_client("competitions:read")), db: Session = Depends(get_db)):
    view = token_view(db, client.token)
    return {k: view[k] for k in ("name", "prefix", "scopes", "expires_on", "author")}


@api.get("/competitions", summary="Календарь соревнований")
def api_competitions(
    state: Literal["open", "closed", "published"] | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    client: ApiClient = Depends(api_client("competitions:read")),
    db: Session = Depends(get_db),
):
    """Опубликованные соревнования (без черновиков), по дате начала."""
    query = select(Competition).where(Competition.state != "draft")
    if state:
        query = query.where(Competition.state == state)
    if date_from:
        query = query.where(Competition.end_date >= date_from)
    if date_to:
        query = query.where(Competition.start_date <= date_to)
    items = db.scalars(query.order_by(Competition.start_date, Competition.id)).all()
    return [competition_data(db, c) for c in items]


@api.get("/competitions/{comp_id}", summary="Соревнование")
def api_competition(
    comp_id: int,
    client: ApiClient = Depends(api_client("competitions:read")),
    db: Session = Depends(get_db),
):
    return competition_data(db, visible_competition(db, comp_id))


@api.get("/competitions/{comp_id}/applications", summary="Одобренные заявки")
def api_applications(
    comp_id: int,
    client: ApiClient = Depends(api_client("applications:read")),
    db: Session = Depends(get_db),
):
    comp = visible_competition(db, comp_id)
    items = db.scalars(
        select(CompetitionApplication)
        .where(
            CompetitionApplication.competition_id == comp.id,
            CompetitionApplication.status == "approved",
        )
        .order_by(CompetitionApplication.id)
    ).all()
    return [application_data(db, a, comp) for a in items]


@api.get("/competitions/{comp_id}/protocol", summary="Протокол (последняя редакция)")
def api_protocol(
    comp_id: int,
    client: ApiClient = Depends(api_client("results:read")),
    db: Session = Depends(get_db),
):
    comp = visible_competition(db, comp_id)
    published = versions(db, comp.id)
    if comp.state != "published" or not published:
        raise HTTPException(404, "Протокол ещё не опубликован")
    return protocol_data(db, comp, published[-1])


@api.post("/competitions/{comp_id}/results", summary="Импорт результатов (JSON)")
def api_import(
    comp_id: int,
    data: ResultsImportIn,
    dry_run: bool = Query(False, description="Только проверить, ничего не сохранять"),
    client: ApiClient = Depends(api_client("results:write")),
    db: Session = Depends(get_db),
):
    """Первая публикация протокола или новая редакция (тогда нужен `reason`).
    Спортсмен — `FSP-000123`, команда — id или название допущенной команды."""
    comp = locked(db, visible_competition(db, comp_id).id)
    return api_audit(db, client, comp, import_results(db, client.actor, comp, data.results, data.reason, dry_run))


@api.post(
    "/competitions/{comp_id}/results.csv",
    summary="Импорт результатов (CSV)",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string"}, "example":
                        "athlete;place;score\nFSP-000001;1;95.5\nFSP-000002;2;80"}},
        }
    },
)
async def api_import_csv(
    comp_id: int,
    request: Request,
    dry_run: bool = Query(False, description="Только проверить, ничего не сохранять"),
    reason: str | None = Query(None, min_length=5, max_length=2000),
    client: ApiClient = Depends(api_client("results:write")),
    db: Session = Depends(get_db),
):
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_IMPORT_SIZE:
            break
    rows = parse_csv(raw)
    comp = locked(db, visible_competition(db, comp_id).id)
    return api_audit(db, client, comp, import_results(db, client.actor, comp, rows, reason, dry_run))


def api_audit(db, client, comp, result):
    if not result["dry_run"]:
        audit(db, client.actor, "Импорт результатов через API", comp,
              {"token": client.token.name, "token_id": client.token.id,
               "count": result["count"], "mode": result["mode"]})
    return result
