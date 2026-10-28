"""External integrations: scoped API tokens, webhooks with an outbox and
import of results from CSV or JSON."""

import csv
import hashlib
import hmac
import io
import ipaddress
import json
import logging
import secrets
import socket
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlsplit
import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import *
from app.schemas import ImportRowIn, ResultIn, ResultsIn, TeamResultIn
from app.security import Actor
from app.services.athlete_ids import parse_athlete_id, public_athlete_id
from app.services.telegram_link import utc

logger = logging.getLogger(__name__)

SCOPES = {
    "competitions:read": "Календарь соревнований",
    "applications:read": "Одобренные заявки участников",
    "results:read": "Опубликованные протоколы",
    "results:write": "Импорт результатов",
}
EVENTS = {
    "competition.published": "Соревнование опубликовано",
    "application.approved": "Заявка одобрена",
    "protocol.published": "Протокол опубликован или исправлен",
}
TOKEN_PREFIX = "ock_"
# minutes before the next attempt; after the last one the delivery fails
RETRY_MINUTES = (1, 5, 15, 60, 240)
MAX_IMPORT_SIZE = 2 * 1024 * 1024


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue_token():
    value = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return value, value[:12], digest(value)


def token_view(db, obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "prefix": obj.prefix,
        "scopes": obj.scopes,
        "created_at": obj.created_at,
        "expires_on": obj.expires_on,
        "last_used_at": obj.last_used_at,
        "revoked_at": obj.revoked_at,
        "active": token_active(obj),
        "author": db.get(User, obj.created_by).full_name,
    }


def token_active(obj):
    return not obj.revoked_at and not (obj.expires_on and obj.expires_on < date.today())


@dataclass
class ApiClient:
    token: ApiToken
    actor: Actor


api_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="ApiToken",
    description="Токен интеграции из раздела «Управление → Интеграции»: "
    "`Authorization: Bearer ock_…`",
)


def api_client(scope):
    """Token of an external system with the given scope. The token acts on
    behalf of the federation employee who issued it while they keep the role."""

    def check(
        credentials: HTTPAuthorizationCredentials | None = Depends(api_bearer),
        db: Session = Depends(get_db),
    ):
        if not credentials or not credentials.credentials.startswith(TOKEN_PREFIX):
            raise HTTPException(401, "Нужен токен интеграции")
        obj = db.scalar(
            select(ApiToken).where(ApiToken.token_hash == digest(credentials.credentials))
        )
        if not obj or not token_active(obj):
            raise HTTPException(401, "Токен отозван, истёк или не существует")
        user = db.get(User, obj.created_by)
        if not user or "admin" not in [r.id for r in user.roles]:
            raise HTTPException(401, "Выпустивший токен сотрудник больше не работает в федерации")
        if scope not in obj.scopes:
            raise HTTPException(403, f"У токена нет права «{scope}»")
        obj.last_used_at = now()
        return ApiClient(obj, Actor(user, "api"))

    return check


# --- webhooks ---------------------------------------------------------------


def internal_address(ip):
    ip = ipaddress.ip_address(ip)
    return not ip.is_global or ip.is_multicast


def resolve(host):
    return {info[4][0] for info in socket.getaddrinfo(host, None)}


def check_url(url, lookup=False):
    """Webhooks go to external systems: internal addresses are refused unless
    WEBHOOK_ALLOW_PRIVATE is set (local demo receivers)."""
    host = urlsplit(url).hostname or ""
    if settings.webhook_allow_private:
        return
    if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
        raise ValueError("Адрес вебхука указывает на внутреннюю сеть")
    try:
        addresses = {str(ipaddress.ip_address(host))}
    except ValueError:
        if not lookup:
            return
        try:
            addresses = resolve(host)
        except OSError:
            raise ValueError("Не удалось найти хост вебхука")
    if any(internal_address(a) for a in addresses):
        raise ValueError("Адрес вебхука указывает на внутреннюю сеть")


def new_secret():
    return "whsec_" + secrets.token_urlsafe(32)


def signature(secret, timestamp, body):
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def emit(db, event, key, data, hooks=None):
    """Queues the event for every active webhook subscribed to it; the key
    keeps a repeated call from sending the same event twice."""
    db.flush()
    hooks = hooks if hooks is not None else db.scalars(
        select(Webhook).where(Webhook.active == True)
    ).all()
    occurred_at = now()
    for hook in hooks:
        # ping is sent to one webhook on request, whatever it subscribes to
        if event != "ping" and event not in hook.events:
            continue
        if db.scalar(
            select(WebhookDelivery.id).where(
                WebhookDelivery.webhook_id == hook.id, WebhookDelivery.event_key == key
            )
        ):
            continue
        db.add(
            WebhookDelivery(
                webhook_id=hook.id,
                event=event,
                event_key=key,
                payload={
                    "id": key,
                    "event": event,
                    "occurred_at": occurred_at.isoformat(),
                    "data": json.loads(json.dumps(data, default=str)),
                },
            )
        )
    db.flush()


def post(url, content, headers):
    with httpx.Client(timeout=5, follow_redirects=False) as client:
        return client.post(url, content=content, headers=headers)


def send(db, delivery):
    hook = db.get(Webhook, delivery.webhook_id)
    body = json.dumps(delivery.payload, ensure_ascii=False).encode()
    timestamp = str(int(now().timestamp()))
    delivery.attempts += 1
    try:
        check_url(hook.url, lookup=True)
        response = post(
            hook.url,
            body,
            {
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "OrenCode-Webhooks/1.0",
                "X-OrenCode-Event": delivery.event,
                "X-OrenCode-Delivery": str(delivery.id),
                "X-OrenCode-Timestamp": timestamp,
                "X-OrenCode-Signature": signature(hook.secret, timestamp, body),
            },
        )
        delivery.response_status = response.status_code
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Получатель ответил кодом {response.status_code}")
        delivery.status, delivery.delivered_at, delivery.last_error = "delivered", now(), None
    except Exception as exc:
        delivery.last_error = str(exc)[:1000] or type(exc).__name__
        if delivery.attempts > len(RETRY_MINUTES):
            delivery.status = "failed"
        else:
            delivery.next_attempt_at = now() + timedelta(
                minutes=RETRY_MINUTES[delivery.attempts - 1]
            )
        logger.warning("Webhook delivery %s failed: %s", delivery.id, type(exc).__name__)


def deliver_webhooks(db, limit=20):
    due = db.scalars(
        select(WebhookDelivery)
        .join(Webhook, Webhook.id == WebhookDelivery.webhook_id)
        .where(
            Webhook.active == True,
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now(),
        )
        .order_by(WebhookDelivery.id)
        .limit(limit)
    ).all()
    for delivery in due:
        send(db, delivery)
        db.commit()


def delivery_view(obj):
    return {
        k: getattr(obj, k)
        for k in (
            "id", "event", "event_key", "status", "attempts", "response_status",
            "last_error", "created_at", "delivered_at", "next_attempt_at", "payload",
        )
    }


# --- event payloads ---------------------------------------------------------


def competition_data(db, comp):
    return {
        "id": comp.id,
        "title": comp.title,
        "discipline": db.get(Discipline, comp.discipline_id).name,
        "type": db.get(CompetitionType, comp.type_id).name,
        "status": comp.status,
        "level": comp.rating_level,
        "state": comp.state,
        "start_date": comp.start_date,
        "end_date": comp.end_date,
        "registration_deadline": comp.deadline,
        "location": comp.location,
        "format": comp.format,
        "entry_mode": comp.entry_mode,
        "min_age": comp.min_age,
        "max_age": comp.max_age,
        "calendar_number": comp.calendar_number,
        "url": f"{settings.public_site_url.rstrip('/')}/competitions/{comp.id}",
    }


def athlete_data(db, athlete_id):
    athlete = db.get(Athlete, athlete_id)
    org = db.get(Organization, athlete.organization_id) if athlete.organization_id else None
    return {
        "athlete_id": public_athlete_id(athlete.id),
        "full_name": athlete.user.full_name,
        "organization": org.name if org else None,
        "municipality": athlete.municipality,
    }


def application_data(db, application, comp):
    group = db.get(AgeGroup, application.age_group_id) if application.age_group_id else None
    team = None
    if comp.entry_mode == "team":
        team = db.scalar(
            select(CompetitionTeam.name)
            .join(CompetitionTeamMember, CompetitionTeamMember.team_id == CompetitionTeam.id)
            .where(
                CompetitionTeam.competition_id == comp.id,
                CompetitionTeam.status == "approved",
                CompetitionTeamMember.athlete_id == application.athlete_id,
            )
        )
    return {
        "application_id": application.id,
        "competition": {"id": comp.id, "title": comp.title},
        **athlete_data(db, application.athlete_id),
        "age_group": group.name if group else None,
        "team_name": team,
        "approved_at": application.approved_at,
    }


def protocol_data(db, comp, version):
    return {
        "competition": competition_data(db, comp),
        "version": version.version,
        "reason": version.reason,
        "published_at": version.created_at,
        "results": [
            {
                "place": e["place"],
                "score": e["score"],
                "athlete_id": public_athlete_id(e["athlete_id"]),
                "full_name": e["full_name"],
                "organization": e["organization"],
                "team_name": e["team_name"],
            }
            for e in version.entries
        ],
    }


def competition_published(db, comp):
    emit(db, "competition.published", f"competition.published:{comp.id}", competition_data(db, comp))


def application_approved(db, application, comp):
    emit(
        db,
        "application.approved",
        f"application.approved:{application.id}:{utc(application.approved_at).isoformat()}",
        application_data(db, application, comp),
    )


def protocol_published(db, comp, version):
    emit(
        db,
        "protocol.published",
        f"protocol.published:{comp.id}:v{version.version}",
        protocol_data(db, comp, version),
    )


# --- import of results ------------------------------------------------------

COLUMNS = {
    "athlete": {"athlete", "athlete_id", "id спортсмена", "спортсмен", "fsp id"},
    "team": {"team", "team_id", "команда", "id команды"},
    "place": {"place", "место"},
    "score": {"score", "баллы", "очки"},
}


def parse_csv(raw):
    if len(raw) > MAX_IMPORT_SIZE:
        raise HTTPException(413, "Файл больше 2 МБ")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel if ";" not in sample else type("Semicolon", (csv.excel,), {"delimiter": ";"})
    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, None)
    if not header:
        raise HTTPException(422, "Файл пустой")
    names = {}
    for i, title in enumerate(header):
        title = title.strip().lower()
        for key, aliases in COLUMNS.items():
            if title in aliases:
                names[key] = i
    if not {"place", "score"} <= set(names) or not {"athlete", "team"} & set(names):
        raise HTTPException(
            422, "Нужны столбцы athlete (или team), place и score — см. пример в описании API"
        )
    rows, errors = [], []
    for line, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        cell = lambda key: values[names[key]].strip() if key in names and names[key] < len(values) else ""
        try:
            rows.append(
                ImportRowIn(
                    athlete=cell("athlete") or None,
                    team=cell("team") or None,
                    place=cell("place"),
                    score=cell("score").replace(",", ".").replace(" ", ""),
                    line=line,
                )
            )
        except ValidationError as exc:
            errors.append(f"Строка {line}: {exc.errors()[0]['msg']}")
    if errors:
        raise HTTPException(422, "; ".join(errors[:20]))
    return rows


def to_results(db, comp, rows, partial=False):
    """Rows identify athletes by FSP-000123 or internal id, teams by id or name.
    A partial import may leave approved participants out of the protocol."""
    if not rows:
        raise HTTPException(422, "В файле нет строк с результатами")
    teams = {}
    if comp.entry_mode == "team":
        for team in db.scalars(
            select(CompetitionTeam).where(
                CompetitionTeam.competition_id == comp.id,
                CompetitionTeam.status == "approved",
            )
        ):
            teams[str(team.id)] = teams[team.name.strip().lower()] = team
    results, team_results, errors = [], [], []
    for i, r in enumerate(rows, start=1):
        where = f"Строка {r.line or i}"
        if comp.entry_mode == "team":
            team = teams.get((r.team or "").strip().lower())
            if not team:
                errors.append(f"{where}: команда «{r.team or ''}» не допущена к соревнованию")
                continue
            team_results.append(TeamResultIn(team_id=team.id, place=r.place, score=r.score))
            continue
        value = (r.athlete or "").strip()
        try:
            athlete_id = int(value) if value.isdigit() else parse_athlete_id(value)
        except HTTPException:
            errors.append(f"{where}: спортсмен «{value}» — нужен ID вида FSP-000123")
            continue
        results.append(ResultIn(athlete_id=athlete_id, place=r.place, score=r.score))
    if comp.entry_mode != "team":
        approved = {
            a.athlete_id: a
            for a in db.scalars(
                select(CompetitionApplication).where(
                    CompetitionApplication.competition_id == comp.id,
                    CompetitionApplication.status == "approved",
                )
            )
        }
        given = [r.athlete_id for r in results]
        errors += [
            f"{public_athlete_id(a)}: нет одобренной заявки на это соревнование"
            for a in dict.fromkeys(given) if a not in approved
        ]
        errors += [
            f"{public_athlete_id(a)}: результат указан несколько раз"
            for a in dict.fromkeys(given) if given.count(a) > 1
        ]
        errors += [
            f"Нет результата участника {db.get(Athlete, a).user.full_name} ({public_athlete_id(a)})"
            for a in approved if a not in given and not partial
        ]
    if errors:
        raise HTTPException(422, "; ".join(errors[:20]))
    try:
        return ResultsIn(results=results, team_results=team_results)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()[0]["msg"])


def preview(db, comp, entries):
    return sorted(
        (
            {**athlete_data(db, e.athlete_id), "place": e.place, "score": e.score,
             "team_name": e.team_name}
            for e in entries
        ),
        key=lambda e: (e["place"], e["team_name"] or "", e["full_name"]),
    )
