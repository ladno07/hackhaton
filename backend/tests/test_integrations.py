import hashlib
import hmac
import json
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.models import *
from app.services import integrations
from app.services.athlete_ids import public_athlete_id
from tests.test_competition_teams import create_coach_team, ok, prepare
from tests.test_ministry import ministry_login
from tests.test_workflows import competition, open_comp


def issue(client, h, scopes, **extra):
    res = client.post(
        "/api/integrations/tokens",
        headers=h["admin"],
        json={"name": "Сайт федерации", "scopes": scopes, **extra},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return {"Authorization": "Bearer " + data["token"]}, data


def hook(client, h, events, url="https://receiver.example.org/hook"):
    res = client.post(
        "/api/integrations/webhooks",
        headers=h["admin"],
        json={"name": "Приёмник", "url": url, "events": events},
    )
    assert res.status_code == 201, res.text
    return res.json()


def finished(client, h, users):
    """Closed competition with the demo athlete approved, ready for a protocol."""
    comp = open_comp(client, h["admin"])
    aid = users["athlete"]["athlete_id"]
    app_id = client.post(
        f"/api/competitions/{comp['id']}/applications",
        headers=h["athlete"],
        json={"athlete_id": aid},
    ).json()["id"]
    res = client.patch(
        f"/api/applications/{app_id}", headers=h["admin"], json={"status": "approved"}
    )
    assert res.status_code == 200, res.text
    res = client.patch(
        f"/api/competitions/{comp['id']}/state", headers=h["admin"], json={"state": "closed"}
    )
    assert res.status_code == 200, res.text
    return comp, aid, app_id


def test_token_scopes_and_revocation(env):
    client, factory, h, users = env
    calendar, info = issue(client, h, ["competitions:read"])
    assert info["token"].startswith("ock_") and info["prefix"] == info["token"][:12]
    # only the hash is kept
    with factory() as db:
        stored = db.get(ApiToken, info["id"])
        assert stored.token_hash == hashlib.sha256(info["token"].encode()).hexdigest()
    listed = client.get("/api/integrations/tokens", headers=h["admin"]).json()
    assert "token" not in listed[0] and listed[0]["active"]

    res = client.get("/api/v1/competitions", headers=calendar)
    assert res.status_code == 200, res.text
    assert res.json() and all(c["state"] != "draft" for c in res.json())
    draft = competition(client, h["admin"])
    assert client.get(f"/api/v1/competitions/{draft['id']}", headers=calendar).status_code == 404
    # the scope is enforced per endpoint
    published = next(c for c in res.json() if c["state"] == "published")
    assert client.get(f"/api/v1/competitions/{published['id']}/protocol", headers=calendar).status_code == 403
    assert client.get("/api/v1/competitions").status_code == 401
    # a session token of the website is not an integration token
    assert client.get("/api/v1/competitions", headers=h["admin"]).status_code == 401
    # website endpoints do not accept integration tokens
    assert client.get("/api/competitions", headers=calendar).status_code == 401

    res = client.delete(f"/api/integrations/tokens/{info['id']}", headers=h["admin"])
    assert res.status_code == 200 and not res.json()["active"]
    assert client.get("/api/v1/competitions", headers=calendar).status_code == 401
    with factory() as db:
        actions = db.scalars(select(AuditLog.action)).all()
        assert "Выпуск токена интеграции" in actions and "Отзыв токена интеграции" in actions


def test_token_expiry_and_issuer_role(env):
    client, factory, h, users = env
    token, info = issue(client, h, ["results:read"])
    published = next(
        c for c in client.get("/api/competitions", headers=h["admin"]).json()
        if c["state"] == "published"
    )
    res = client.get(f"/api/v1/competitions/{published['id']}/protocol", headers=token)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] >= 1 and body["results"][0]["athlete_id"].startswith("FSP-")
    with factory() as db:
        db.get(ApiToken, info["id"]).expires_on = date.today() - timedelta(days=1)
        db.commit()
    assert client.get(f"/api/v1/competitions/{published['id']}/protocol", headers=token).status_code == 401
    with factory() as db:
        db.get(ApiToken, info["id"]).expires_on = None
        db.query(UserRole).filter(
            UserRole.user_id == users["admin"]["id"], UserRole.role_id == "admin"
        ).delete()
        db.commit()
    assert client.get(f"/api/v1/competitions/{published['id']}/protocol", headers=token).status_code == 401


@pytest.mark.parametrize("role", ["athlete", "coach", "judge"])
def test_management_is_admin_only(env, role):
    client, factory, h, users = env
    for url in ["/api/integrations/tokens", "/api/integrations/webhooks"]:
        assert client.get(url, headers=h[role]).status_code == 403
    assert client.post(
        "/api/integrations/tokens",
        headers=h[role],
        json={"name": "Чужой", "scopes": ["results:write"]},
    ).status_code == 403


def test_ministry_cannot_issue_tokens(env):
    client, factory, h, users = env
    ministry = ministry_login(client)
    assert client.post(
        "/api/integrations/tokens",
        headers=ministry,
        json={"name": "Минспорт", "scopes": ["results:read"]},
    ).status_code == 403


def test_webhook_url_rejects_internal_addresses(env):
    client, factory, h, users = env
    for url in ["http://localhost:8000/x", "http://127.0.0.1/x", "http://10.0.0.5/x", "ftp://example.org/x"]:
        res = client.post(
            "/api/integrations/webhooks",
            headers=h["admin"],
            json={"name": "Внутренний", "url": url, "events": ["protocol.published"]},
        )
        assert res.status_code == 422, url


def test_events_are_queued_signed_and_retried(env, monkeypatch):
    client, factory, h, users = env
    created = hook(client, h, ["competition.published", "application.approved", "protocol.published"])
    only_protocol = hook(client, h, ["protocol.published"])
    assert created["secret"].startswith("whsec_")
    assert "secret" not in client.get("/api/integrations/webhooks", headers=h["admin"]).json()[0]

    comp, aid, app_id = finished(client, h, users)
    # reopening registration does not publish the competition again
    client.patch(f"/api/competitions/{comp['id']}/state", headers=h["admin"], json={"state": "open"})
    client.patch(f"/api/competitions/{comp['id']}/state", headers=h["admin"], json={"state": "closed"})
    res = client.post(
        f"/api/competitions/{comp['id']}/results",
        headers=h["admin"],
        json={"results": [{"athlete_id": aid, "place": 1, "score": 90}]},
    )
    assert res.status_code == 200, res.text
    res = client.put(
        f"/api/competitions/{comp['id']}/results",
        headers=h["admin"],
        json={"results": [{"athlete_id": aid, "place": 1, "score": 91}], "reason": "Пересчёт баллов"},
    )
    assert res.status_code == 200, res.text

    with factory() as db:
        events = db.scalars(
            select(WebhookDelivery.event)
            .where(WebhookDelivery.webhook_id == created["id"])
            .order_by(WebhookDelivery.id)
        ).all()
        assert events == [
            "competition.published", "application.approved",
            "protocol.published", "protocol.published",
        ]
        assert db.scalars(
            select(WebhookDelivery.event).where(WebhookDelivery.webhook_id == only_protocol["id"])
        ).all() == ["protocol.published", "protocol.published"]

    sent = []

    def receiver(url, content, headers):
        sent.append((url, content, headers))
        return type("Response", (), {"status_code": 500 if len(sent) == 1 else 204})()

    monkeypatch.setattr(integrations, "post", receiver)
    monkeypatch.setattr(integrations, "resolve", lambda host: {"93.184.216.34"})
    with factory() as db:
        integrations.deliver_webhooks(db)
    assert len(sent) == 6
    url, content, headers = sent[1]
    payload = json.loads(content)
    assert headers["X-OrenCode-Event"] == payload["event"] == "application.approved"
    assert payload["data"]["athlete_id"] == public_athlete_id(aid)
    expected = hmac.new(
        created["secret"].encode(),
        headers["X-OrenCode-Timestamp"].encode() + b"." + content,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-OrenCode-Signature"] == "sha256=" + expected
    protocol = json.loads(sent[4][1])
    assert protocol["data"]["version"] == 2 and protocol["data"]["results"][0]["score"] == 91

    # the failed one waits for the retry, the rest are delivered
    log = client.get(f"/api/integrations/webhooks/{created['id']}/deliveries", headers=h["admin"]).json()
    failed = next(d for d in log if d["status"] == "pending")
    assert failed["event"] == "competition.published" and failed["response_status"] == 500
    assert failed["attempts"] == 1 and "500" in failed["last_error"]
    assert sum(d["status"] == "delivered" for d in log) == 3
    with factory() as db:
        integrations.deliver_webhooks(db)
    assert len(sent) == 6  # not due yet
    res = client.post(f"/api/integrations/deliveries/{failed['id']}/retry", headers=h["admin"])
    assert res.status_code == 200
    with factory() as db:
        integrations.deliver_webhooks(db)
    assert len(sent) == 7
    assert client.post(f"/api/integrations/deliveries/{failed['id']}/retry", headers=h["admin"]).status_code == 409


def test_delivery_gives_up_and_skips_disabled_webhooks(env, monkeypatch):
    client, factory, h, users = env
    created = hook(client, h, ["competition.published"])
    monkeypatch.setattr(integrations, "resolve", lambda host: {"10.1.2.3"})
    calls = []
    monkeypatch.setattr(integrations, "post", lambda *a: calls.append(a))
    open_comp(client, h["admin"])
    for _ in range(len(integrations.RETRY_MINUTES) + 1):
        with factory() as db:
            db.query(WebhookDelivery).update({"next_attempt_at": now()})
            db.commit()
            integrations.deliver_webhooks(db)
    log = client.get(f"/api/integrations/webhooks/{created['id']}/deliveries", headers=h["admin"]).json()
    # the host now resolves to an internal network: nothing is sent
    assert not calls and log[0]["status"] == "failed"
    assert "внутреннюю сеть" in log[0]["last_error"]

    res = client.patch(f"/api/integrations/webhooks/{created['id']}", headers=h["admin"], json={"active": False})
    assert res.status_code == 200 and not res.json()["active"]
    open_comp(client, h["admin"])
    with factory() as db:
        assert db.query(WebhookDelivery).count() == 1
    assert client.post(f"/api/integrations/webhooks/{created['id']}/test", headers=h["admin"]).status_code == 409
    client.patch(f"/api/integrations/webhooks/{created['id']}", headers=h["admin"], json={"active": True})
    assert client.post(f"/api/integrations/webhooks/{created['id']}/test", headers=h["admin"]).status_code == 202
    with factory() as db:
        assert db.scalars(select(WebhookDelivery.event).order_by(WebhookDelivery.id.desc())).first() == "ping"
    assert client.delete(f"/api/integrations/webhooks/{created['id']}", headers=h["admin"]).status_code == 204
    with factory() as db:
        assert db.query(WebhookDelivery).count() == 0


def test_team_approval_emits_event(env):
    client, factory, h, users, base, people = prepare(env)
    hook(client, h, ["application.approved"])
    team, url = create_coach_team(client, h, base, people, name="Импорт")
    for headers, _ in people[:2]:
        ok(client.patch(url + "/response", headers=headers, json={"status": "accepted"}))
    ok(client.post(url + "/submit", headers=h["coach"]))
    ok(client.patch(url + "/review", headers=h["admin"], json={"status": "approved"}))
    with factory() as db:
        payloads = db.scalars(
            select(WebhookDelivery.payload).where(WebhookDelivery.event == "application.approved")
        ).all()
    assert sorted(p["data"]["athlete_id"] for p in payloads) == sorted(
        public_athlete_id(aid) for _, aid in people[:2]
    )
    assert all(p["data"]["team_name"] == "Импорт" and p["data"]["approved_at"] for p in payloads)


def test_import_csv_dry_run_and_publish(env):
    client, factory, h, users = env
    comp, aid, _ = finished(client, h, users)
    fsp = public_athlete_id(aid)

    def upload(text, **form):
        return client.post(
            f"/api/competitions/{comp['id']}/results/import",
            headers=h["admin"],
            files={"file": ("results.csv", text.encode("utf-8-sig"), "text/csv")},
            data=form,
        )

    res = upload("athlete;place\n" + fsp + ";1")
    assert res.status_code == 422 and "score" in res.text
    res = upload("athlete;place;score\nFSP-999999;1;10\n")
    assert res.status_code == 422
    assert "FSP-999999: нет одобренной заявки" in res.text and "Нет результата участника" in res.text
    res = upload("athlete;place;score\nкто-то;1;10\n")
    assert res.status_code == 422 and "Строка 2" in res.text

    res = upload(f"Спортсмен;Место;Баллы\n{fsp};1;95,5\n")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dry_run"] and body["mode"] == "publication"
    assert body["rows"][0]["athlete_id"] == fsp and body["rows"][0]["score"] == 95.5
    assert client.get(f"/api/competitions/{comp['id']}", headers=h["admin"]).json()["state"] == "closed"

    res = upload(f"athlete,place,score\n{fsp},1,95.5\n", dry_run="false")
    assert res.status_code == 200, res.text
    assert res.json()["version"] == 1
    assert client.get(f"/api/competitions/{comp['id']}", headers=h["admin"]).json()["state"] == "published"

    # a published protocol is corrected only with a reason
    res = upload(f"athlete;place;score\n{fsp};1;97\n", dry_run="false")
    assert res.status_code == 422 and "основание" in res.text
    res = upload(f"athlete;place;score\n{fsp};1;97\n", dry_run="false", reason="Протест принят")
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "correction" and res.json()["version"] == 2
    with factory() as db:
        assert "Импорт результатов из файла" in db.scalars(select(AuditLog.action)).all()


def test_import_through_api(env):
    client, factory, h, users = env
    comp, aid, _ = finished(client, h, users)
    reader, _ = issue(client, h, ["results:read", "applications:read"])
    writer, info = issue(client, h, ["results:write"])
    url = f"/api/v1/competitions/{comp['id']}/results"
    body = {"results": [{"athlete": public_athlete_id(aid), "place": 1, "score": 88}]}
    assert client.post(url, headers=reader, json=body).status_code == 403

    participants = client.get(f"/api/v1/competitions/{comp['id']}/applications", headers=reader)
    assert participants.status_code == 200, participants.text
    assert [p["athlete_id"] for p in participants.json()] == [public_athlete_id(aid)]
    assert "birth_date" not in participants.json()[0]

    res = client.post(url + "?dry_run=true", headers=writer, json=body)
    assert res.status_code == 200 and res.json()["dry_run"]
    assert client.get(f"/api/v1/competitions/{comp['id']}/protocol", headers=reader).status_code == 404
    res = client.post(url, headers=writer, json=body)
    assert res.status_code == 200, res.text
    protocol = client.get(f"/api/v1/competitions/{comp['id']}/protocol", headers=reader).json()
    assert protocol["version"] == 1 and protocol["results"][0]["score"] == 88

    res = client.post(
        url + ".csv?reason=Исправление%20ошибки",
        headers={**writer, "Content-Type": "text/csv"},
        content=f"athlete;place;score\n{aid};1;89\n".encode(),
    )
    assert res.status_code == 200, res.text
    assert res.json()["version"] == 2
    with factory() as db:
        entry = db.scalars(
            select(AuditLog).where(AuditLog.action == "Импорт результатов через API")
        ).all()
        assert len(entry) == 2 and entry[0].active_role == "api"
        assert entry[0].details["token_id"] == info["id"]
        assert db.get(ApiToken, info["id"]).last_used_at is not None
