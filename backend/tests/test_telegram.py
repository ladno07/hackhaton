from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select, func
from app.config import settings
from app.models import *
from app.services.notifications import notify
from app.services.telegram_link import issue, claim, disconnect, utc, digest
from bot.schedule import current_reminders, schedule, roles_for
from bot.delivery import deliver, notice_roles
from bot.handlers import handle
from bot.telegram import TelegramError
from bot.views import render
from bot.views import button
from bot.telegram import Telegram
from bot.__main__ import process_update
from test_workflows import open_comp


class FakeTelegram:
    def __init__(self, error=None):
        self.messages = []
        self.calls = []
        self.error = error

    def send(self, chat_id, text, keyboard=None):
        if self.error:
            raise self.error
        self.messages.append((chat_id, text, keyboard))
        return {"message_id": 1000 + len(self.messages)}

    def call(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return True


@pytest.fixture(autouse=True)
def bot_settings(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_bot_username", "fsp_test_bot")


def token_for(db, user_id, at=None):
    data = issue(db, user_id, at)
    return data["code"]


def connect(db, user_id, chat_id=101, at=None):
    token = token_for(db, user_id, at)
    claim(db, token, chat_id, at=at)
    link = claim(db, token, chat_id, confirm=True, at=at)
    db.commit()
    return link


def competition_at(env, start, start_time=time(12), accepted=True):
    client, factory, headers, users = env
    comp = open_comp(client, headers["admin"], start_date=start.isoformat(), end_date=start.isoformat(),
                     deadline=start.isoformat(), start_time=start_time.isoformat() if start_time else None)
    if accepted:
        with factory() as db:
            db.add(CompetitionApplication(competition_id=comp["id"], athlete_id=users["athlete"]["athlete_id"],
                                         submitted_by=users["athlete"]["id"], status="approved"))
            db.commit()
    return comp


def test_link_api_tokens_and_confirmation(env):
    client, factory, h, users = env
    assert client.get("/api/telegram/link").status_code == 403
    assert client.get("/api/telegram/link", headers=h["athlete"]).json()["available"]
    first = client.post("/api/telegram/link-code", headers=h["athlete"]).json()
    assert len(first["code"]) == 8 and first["code"].isdigit()
    assert "?start=" not in first["bot_url"]
    old_token = first["code"]
    with factory() as db:
        token = token_for(db, users["athlete"]["id"])
        assert db.get(TelegramLinkToken, users["athlete"]["id"]).token_hash == digest(token)
        with pytest.raises(ValueError):
            claim(db, old_token, 101)
        with pytest.raises(ValueError):
            claim(db, token, 101, confirm=True)
        claim(db, token, 101)
        with pytest.raises(ValueError):
            claim(db, token, 102)
        claim(db, token, 101, confirm=True)
        db.commit()
        with pytest.raises(ValueError):
            claim(db, token, 101, confirm=True)
    assert client.get("/api/telegram/link", headers=h["athlete"]).json()["connected"]
    assert not client.get("/api/telegram/link", headers=h["judge"]).json()["connected"]
    assert client.post("/api/telegram/link-token", headers=h["athlete"]).status_code == 409
    assert client.delete("/api/telegram/link", headers=h["judge"]).status_code == 204
    assert client.get("/api/telegram/link", headers=h["athlete"]).json()["connected"]
    assert client.delete("/api/telegram/link", headers=h["athlete"]).status_code == 204
    assert not client.get("/api/telegram/link", headers=h["athlete"]).json()["connected"]


def test_expired_and_occupied_link(env):
    _, factory, _, users = env
    at = datetime(2026, 10, 27, tzinfo=timezone.utc)
    with factory() as db:
        token = token_for(db, users["athlete"]["id"], at)
        with pytest.raises(ValueError):
            claim(db, token, 101, at=at + timedelta(minutes=10))
        connect(db, users["athlete"]["id"], at=at)
        token = token_for(db, users["judge"]["id"], at)
        with pytest.raises(ValueError):
            claim(db, token, 101, at=at)


def test_disabled_bot_does_not_break_site(env, monkeypatch):
    client, _, h, _ = env
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    assert client.get("/api/telegram/link", headers=h["athlete"]).json()["available"] is False
    assert client.post("/api/telegram/link-token", headers=h["athlete"]).status_code == 503
    assert client.get("/api/competitions", headers=h["athlete"]).status_code == 200


def test_no_history_and_independent_delivery(env):
    client, factory, h, users = env
    api = FakeTelegram()
    with factory() as db:
        uid = users["athlete"]["id"]
        notify(db, [uid], "Старое", "Не отправлять", "test:old")
        db.commit()
        link = connect(db, uid)
        notify(db, [uid], "Новое", "Проверка", "test:new")
        db.commit()
        deliver(db, api)
        assert len(api.messages) == 1
        notice = db.scalar(select(Notification).where(Notification.event_key == "test:new"))
        assert notice.mailed_at is None
        assert db.scalar(select(TelegramDelivery).where(TelegramDelivery.notification_id == notice.id)).status == "sent"
        deliver(db, api)
        assert len(api.messages) == 1
        disconnect(db, link)
        notify(db, [uid], "Отключено", "Не отправлять", "test:disconnected")
        db.commit()
        connect(db, uid)
        deliver(db, api)
        assert len(api.messages) == 1
    notices = client.get("/api/notifications", headers=h["athlete"]).json()
    assert next(n for n in notices if n["event_key"] == "test:new")["telegram_delivery"]["status"] == "sent"


def test_delivery_retry_and_block(env):
    _, factory, _, users = env
    at = datetime.now(timezone.utc)
    with factory() as db:
        link = connect(db, users["athlete"]["id"])
        notify(db, [link.user_id], "Событие", "Текст", "test:retry")
        db.commit()
        deliver(db, FakeTelegram(TelegramError(429, 120)), at)
        delivery = db.scalar(select(TelegramDelivery).where(TelegramDelivery.link_id == link.id))
        assert delivery.attempts == 1 and delivery.status == "pending"
        assert utc(delivery.next_attempt_at) == at + timedelta(seconds=120)
        deliver(db, FakeTelegram(TelegramError(403)), at + timedelta(seconds=121))
        assert delivery.status == "blocked"
        assert link.blocked_at and not link.active
        disconnect(db, link)
        db.commit()
        assert link.blocked_at is None
        connect(db, users["athlete"]["id"])


def test_private_chat_and_role_forgery(env):
    _, factory, _, users = env
    api = FakeTelegram()
    with factory() as db:
        link = connect(db, users["athlete"]["id"])
        update = {"message": {"from": {"id": 101}, "chat": {"id": -100, "type": "group"}, "text": "/start"}}
        handle(db, api, update)
        assert not api.messages
        callback = {"callback_query": {"id": "1", "from": {"id": 101}, "data": "role:admin",
                    "message": {"chat": {"id": 101, "type": "private"}}}}
        handle(db, api, callback)
        assert link.role == "athlete"
        assert "недоступен" in api.messages[-1][1]
        callback["callback_query"]["data"] = "view:assignments:0"
        handle(db, api, callback)
        assert "доступен судьям" in api.messages[-1][1]
        handle(db, api, private_callback("view:logout:0"))
        assert not link.active


@pytest.mark.parametrize("start_time,hour,expected", [(time(12), 9, "0"), (time(8), 7, "hour"), (None, 9, "0")])
def test_schedule_start_boundaries(env, start_time, hour, expected):
    start = date.today() + timedelta(days=5)
    comp = competition_at(env, start, start_time)
    _, factory, _, users = env
    at = datetime.combine(start, time(hour), ZoneInfo("Asia/Yekaterinburg"))
    with factory() as db:
        candidates = current_reminders(db, at)
        starts = [r for r in candidates.values() if r.user_id == users["athlete"]["id"] and r.key.startswith(f"tg-reminder:start:{comp['id']}:")]
        assert len(starts) == 1 and starts[0].key.endswith(":" + expected)
        if start_time:
            after = datetime.combine(start, start_time, ZoneInfo("Asia/Yekaterinburg"))
            assert not any(r.key.startswith(f"tg-reminder:start:{comp['id']}:") for r in current_reminders(db, after).values())


def test_latest_reminder_and_revoked_admission(env):
    start = date.today() + timedelta(days=5)
    comp = competition_at(env, start)
    _, factory, _, users = env
    at = datetime.combine(start - timedelta(days=3), time(9), ZoneInfo("Asia/Yekaterinburg"))
    api = FakeTelegram()
    with factory() as db:
        connect(db, users["athlete"]["id"], at=at)
        schedule(db, at)
        db.commit()
        count = db.scalar(select(func.count(Notification.id)))
        schedule(db, at)
        assert db.scalar(select(func.count(Notification.id))) == count
        # A restart on the morning of the competition must cancel the old stage.
        later = datetime.combine(start, time(9), ZoneInfo("Asia/Yekaterinburg"))
        schedule(db, later)
        db.commit()
        deliver(db, api, later)
        starts = [message for message in api.messages if "Напоминание о соревновании" in message[1]]
        assert len(starts) == 1
        app = db.scalar(select(CompetitionApplication).where(CompetitionApplication.competition_id == comp["id"]))
        app.status = "rejected"
        db.commit()
        assert not any(r.key.startswith(f"tg-reminder:start:{comp['id']}:") and r.user_id == users["athlete"]["id"]
                       for r in current_reminders(db, later).values())


def test_competition_reminders_require_approved_application(env):
    start = date.today() + timedelta(days=10)
    comp = competition_at(env, start, accepted=False)
    _, factory, _, users = env
    at = datetime.combine(start - timedelta(days=3), time(9), ZoneInfo("Asia/Yekaterinburg"))
    with factory() as db:
        uid = users["athlete"]["id"]
        assert not any(r.user_id == uid and r.key.startswith(f"tg-reminder:start:{comp['id']}:") for r in current_reminders(db, at).values())
        application = CompetitionApplication(competition_id=comp["id"], athlete_id=users["athlete"]["athlete_id"],
                                             submitted_by=uid, status="pending")
        db.add(application)
        db.flush()
        assert not any(r.user_id == uid and r.key.startswith(f"tg-reminder:registration:{comp['id']}:") for r in current_reminders(db, at).values())
        assert not any(r.user_id == uid and r.key.startswith(f"tg-reminder:start:{comp['id']}:") for r in current_reminders(db, at).values())
        application.status, application.approved_at = "approved", at - timedelta(days=1)
        db.flush()
        assert any(r.user_id == uid and r.key.startswith(f"tg-reminder:start:{comp['id']}:") for r in current_reminders(db, at).values())


def test_schedule_api_and_stale_delivery(env):
    start = date.today() + timedelta(days=5)
    comp = competition_at(env, start)
    client, factory, h, users = env
    data = {"start_date": str(start + timedelta(days=1)), "end_date": str(start + timedelta(days=1)), "start_time": "14:00", "timezone": "Asia/Yekaterinburg"}
    assert client.patch(f"/api/competitions/{comp['id']}/schedule", headers=h["athlete"], json=data).status_code == 403
    bad = {**data, "timezone": "Bad/Zone"}
    assert client.patch(f"/api/competitions/{comp['id']}/schedule", headers=h["admin"], json=bad).status_code == 422
    at = datetime.combine(start - timedelta(days=3), time(9), ZoneInfo("Asia/Yekaterinburg"))
    with factory() as db:
        connect(db, users["athlete"]["id"], at=at)
        schedule(db, at)
        db.commit()
    assert client.patch(f"/api/competitions/{comp['id']}/schedule", headers=h["admin"], json=data).status_code == 200
    with factory() as db:
        api = FakeTelegram()
        deliver(db, api, at)
        moved = [message for message in api.messages if "расписание" in message[1]]
        assert len(moved) == 1
        assert db.scalar(select(TelegramDelivery).join(Notification).where(Notification.event_key.like("tg-reminder:start:%"))).status == "cancelled"


def test_role_pagination_and_no_foreign_applications(env):
    client, factory, h, users = env
    for i in range(6):
        open_comp(client, h["admin"], title=f"Турнир {i}")
    with factory() as db:
        link = connect(db, users["athlete"]["id"])
        user = db.get(User, link.user_id)
        body, keyboard = render(db, link, user, "competitions", 0)
        assert len([row for row in keyboard if row[0].get("url") or row[0].get("callback_data", "").startswith("site:")]) == 5
        assert any(b.get("callback_data") == "view:competitions:1" for row in keyboard for b in row)
        body, _ = render(db, link, user, "applications", 0)
        assert users["athlete"]["full_name"] in body
        assert users["coach"]["full_name"] not in body
        judge = db.scalar(select(Judge).where(Judge.user_id == users["judge"]["id"]))
        judge.archived_at = now()
        db.flush()
        assert "judge" not in roles_for(db, judge.user_id)


def test_discipline_scoped_coach_judge_and_role_removal(env):
    start = date.today() + timedelta(days=5)
    comp = competition_at(env, start)
    _, factory, _, users = env
    at = datetime.combine(start - timedelta(days=3), time(9), ZoneInfo("Asia/Yekaterinburg"))
    with factory() as db:
        aid = users["athlete"]["athlete_id"]
        coach_id = users["coach"]["coach_id"]
        coach_uid = users["coach"]["id"]
        judge_uid = users["judge"]["id"]
        db.add(AthleteCoach(athlete_id=aid, coach_id=coach_id, discipline_id=2, status="active"))
        db.add(CompetitionJudge(competition_id=comp["id"], judge_id=users["judge"]["judge_id"], position="Судья"))
        db.flush()

        def recipients():
            return {r.user_id for r in current_reminders(db, at).values() if r.key.startswith(f"tg-reminder:start:{comp['id']}:")}

        assert coach_uid not in recipients()
        assert judge_uid not in recipients()
        relation = AthleteCoach(athlete_id=aid, coach_id=coach_id, discipline_id=1, status="active")
        db.add(relation)
        db.flush()
        assert coach_uid not in recipients()
        relation.status = "ended"
        db.flush()
        assert coach_uid not in recipients()
        assignment = db.get(CompetitionJudge, (comp["id"], users["judge"]["judge_id"]))
        db.delete(assignment)
        db.flush()
        assert judge_uid not in recipients()
        role = db.get(UserRole, (judge_uid, "judge"))
        db.delete(role)
        db.flush()
        assert "judge" not in roles_for(db, judge_uid)


def test_demo_workflow_delivers_decision_judge_and_protocol(env):
    client, factory, h, users = env
    with factory() as db:
        connect(db, users["athlete"]["id"], 101)
        connect(db, users["judge"]["id"], 102)
    comp = open_comp(client, h["admin"])
    cid = comp["id"]
    aid = users["athlete"]["athlete_id"]
    app = client.post(f"/api/competitions/{cid}/applications", headers=h["athlete"], json={"athlete_id": aid}).json()
    assert client.patch(f"/api/applications/{app['id']}", headers=h["admin"], json={"status": "approved", "comment": "Допущен"}).status_code == 200
    assert client.post(f"/api/competitions/{cid}/judges", headers=h["admin"], json={"judge_id": users["judge"]["judge_id"], "position": "Главный судья"}).status_code == 201
    assert client.patch(f"/api/competitions/{cid}/state", headers=h["admin"], json={"state": "closed"}).status_code == 200
    assert client.post(f"/api/competitions/{cid}/results", headers=h["admin"], json={"results": [{"athlete_id": aid, "place": 1, "score": 100}]}).status_code == 200
    api = FakeTelegram()
    with factory() as db:
        deliver(db, api)
    athlete_messages = [text for chat, text, _ in api.messages if chat == 101]
    judge_messages = [text for chat, text, _ in api.messages if chat == 102]
    assert any("одобрена" in text and "Допущен" in text for text in athlete_messages)
    assert any("Опубликован протокол" in text for text in athlete_messages)
    assert not judge_messages


def private_message(text, update_id=1, chat_id=101):
    return {"update_id": update_id, "message": {"from": {"id": chat_id},
            "chat": {"id": chat_id, "type": "private"}, "text": text}}


def private_callback(data, update_id=1, chat_id=101):
    return {"update_id": update_id, "callback_query": {"id": str(update_id), "from": {"id": chat_id},
            "message": {"message_id": 500, "chat": {"id": chat_id, "type": "private"}}, "data": data}}


def test_pairing_code_message_confirmation_and_reuse(env):
    client, factory, h, users = env
    issued = client.post("/api/telegram/link-code", headers=h["athlete"]).json()
    code = issued["code"]
    api = FakeTelegram()
    with factory() as db:
        handle(db, api, private_message("/start"))
        assert "8-значный" in api.messages[-1][1]
        handle(db, api, private_message(code[:4] + " " + code[4:]))
        assert users["athlete"]["full_name"] in api.messages[-1][1]
        confirm = api.messages[-1][2][0][0]["callback_data"]
        assert confirm == f"confirm:{code}"
        assert not db.scalar(select(TelegramLink).where(TelegramLink.user_id == users["athlete"]["id"]))
        handle(db, api, private_callback(confirm, 2))
        assert "Telegram подключён" in api.messages[-1][1]
        assert db.get(TelegramLinkToken, users["athlete"]["id"]) is None
        handle(db, api, private_callback(confirm, 3))
        assert "уже использован" in api.messages[-1][1]


def test_bad_code_attempts_persist_and_expire(env):
    _, factory, _, users = env
    at = datetime.now(timezone.utc)
    api = FakeTelegram()
    for i in range(6):
        with factory() as db:
            handle(db, api, private_message("00000000", i))
    assert "Слишком много попыток" in api.messages[-1][1]
    with factory() as db:
        entry = db.get(TelegramCodeAttempt, 101)
        assert entry.attempts == 5
        code = token_for(db, users["athlete"]["id"], at + timedelta(minutes=11))
        claim(db, code, 101, at=at + timedelta(minutes=11))
        claim(db, code, 101, confirm=True, at=at + timedelta(minutes=11))
        db.commit()


def test_localhost_buttons_and_local_link_callback(env, monkeypatch):
    _, factory, _, users = env
    monkeypatch.setattr(settings, "public_site_url", "http://localhost:8080")
    link_button = button("Открыть", path="/competitions/1")
    assert link_button["url"] == "http://127.0.0.1:8080/competitions/1" and "callback_data" not in link_button
    api = FakeTelegram()
    with factory() as db:
        connect(db, users["athlete"]["id"])
        # Buttons already sent by an older version remain safe to click.
        handle(db, api, private_callback("site:/competitions/1"))
        assert "http://127.0.0.1:8080/competitions/1" in api.messages[-1][1]
        assert "компьютере" in api.messages[-1][1]
    monkeypatch.setattr(settings, "public_site_url", "https://fsp.example.org")
    assert button("Открыть", path="/notifications")["url"] == "https://fsp.example.org/notifications"


def test_telegram_adapter_falls_back_after_rejected_url():
    import httpx
    import json
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "Bad Request: BUTTON_URL_INVALID"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    api = Telegram()
    api.client.close()
    api.client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        api.send(101, "Информация", [[{"text": "Сайт", "url": "http://localhost:8080"}], [button("Меню", "view:menu:0")]])
        assert len(calls) == 2
        assert "http://localhost:8080" in calls[1]["text"]
        assert calls[1]["reply_markup"]["inline_keyboard"] == [[button("Меню", "view:menu:0")]]
    finally:
        api.close()


def test_permanent_callback_failure_does_not_block_updates(env):
    _, factory, _, users = env

    class RejectOnce(FakeTelegram):
        def __init__(self):
            super().__init__()
            self.rejected = False

        def send(self, chat_id, text, keyboard=None):
            if not self.rejected:
                self.rejected = True
                raise TelegramError(400, method="sendMessage", reason="button_url")
            super().send(chat_id, text, keyboard)

    api = RejectOnce()
    with factory() as db:
        connect(db, users["athlete"]["id"])
        process_update(db, api, private_callback("view:competitions:0", 41))
        assert db.get(TelegramCursor, 1).update_id == 41
        assert api.messages
        process_update(db, api, private_callback("view:roles:0", 42))
        assert db.get(TelegramCursor, 1).update_id == 42
        assert "Выберите роль" in api.messages[-1][1]


def test_transient_callback_failure_keeps_cursor_for_retry(env):
    _, factory, _, users = env
    with factory() as db:
        connect(db, users["athlete"]["id"])
        db.add(TelegramCursor(id=1, update_id=40))
        db.commit()
        with pytest.raises(TelegramError):
            process_update(db, FakeTelegram(TelegramError(0)), private_callback("view:roles:0", 41))
        assert db.get(TelegramCursor, 1).update_id == 40


def test_menu_order_links_and_only_start_command(env, monkeypatch):
    from bot.views import menu
    from bot.__main__ import COMMANDS
    assert COMMANDS == [{"command": "start", "description": "Открыть меню"}]
    labels = [b["text"] for row in menu("admin") for b in row]
    assert labels[0] == "👤 Личный кабинет"
    assert labels[-2:] == ["🔄 Выбор роли", "🚪 Выход из аккаунта"]
    assert "🚪 Выход из аккаунта" in labels and "Настройки" not in labels and "Кабинет" not in labels
    _, factory, _, users = env
    with factory() as db:
        link = connect(db, users["athlete"]["id"])
        _, keyboard = render(db, link, db.get(User, link.user_id), "competitions", 0)
        competition_links = [b for row in keyboard for b in row if "/competitions/" in b.get("url", "")]
        assert competition_links and all("callback_data" not in b for b in competition_links)


def test_own_profile_live_data_excludes_rusada_and_secrets(env):
    _, factory, _, users = env
    with factory() as db:
        link = connect(db, users["athlete"]["id"])
        user = db.get(User, link.user_id)
        athlete = db.get(Athlete, users["athlete"]["athlete_id"])
        athlete.rusada_certificate = "https://private.example/DO-NOT-SEND"
        athlete.rusada_date = date.today()
        athlete.training_stage = "Тестовый этап подготовки"
        db.flush()
        body, _ = render(db, link, user, "profile", 0)
        assert user.full_name in body and user.email in body
        assert "Тестовый этап подготовки" in body and "Дисциплины и годы" in body
        assert "РУСАДА" not in body and "DO-NOT-SEND" not in body and user.password_hash not in body
        assert users["judge"]["email"] not in body
        athlete.training_stage = "Изменено на сайте"
        db.flush()
        assert "Изменено на сайте" in render(db, link, user, "profile", 0)[0]


@pytest.mark.parametrize("role", ["coach", "judge"])
def test_staff_profile_is_own_and_role_specific(env, role):
    _, factory, _, users = env
    with factory() as db:
        link = connect(db, users[role]["id"])
        link.role = role
        user = db.get(User, link.user_id)
        model = Coach if role == "coach" else Judge
        card = db.scalar(select(model).where(model.user_id == user.id))
        card.phone = "+7 000 000 00 01"
        card.qualification = "Тестовая квалификация"
        db.flush()
        body, _ = render(db, link, user, "profile", 0)
        assert card.phone in body and card.qualification in body
        assert user.email in body and users["athlete"]["email"] not in body


def test_tab_navigation_sends_then_deletes_previous_screen(env):
    _, factory, _, users = env
    events = []

    class RecordingTelegram(FakeTelegram):
        def send(self, chat_id, text, keyboard=None):
            events.append("send")
            return super().send(chat_id, text, keyboard)

        def call(self, method, **kwargs):
            events.append(method)
            return super().call(method, **kwargs)

    api = RecordingTelegram()
    with factory() as db:
        connect(db, users["admin"]["id"])
        for section in ("profile", "competitions", "applications", "deadlines", "assignments", "roles", "menu"):
            events.clear()
            handle(db, api, private_callback(f"view:{section}:0"))
            assert events.index("send") < events.index("deleteMessage")
            assert api.calls[-1] == ("deleteMessage", {"chat_id": 101, "message_id": 500})


def test_logout_button_disconnects_and_old_commands_do_not(env):
    _, factory, _, users = env
    api = FakeTelegram()
    with factory() as db:
        link = connect(db, users["athlete"]["id"])
        for command in ("/help", "/settings", "/stop", "/link 12345678"):
            handle(db, api, private_message(command))
            assert link.active and "Доступна команда /start" in api.messages[-1][1]
        handle(db, api, private_callback("view:logout:0"))
        assert not link.active and link.chat_id is None
        assert "Вы вышли из аккаунта" in api.messages[-1][1]
        handle(db, api, private_callback("view:profile:0"))
        assert "8-значный" in api.messages[-1][1]


def test_failed_screen_send_keeps_previous_message():
    from bot.navigation import reply_screen
    api = FakeTelegram(TelegramError(0))
    with pytest.raises(TelegramError):
        reply_screen(api, 101, "Следующий раздел", previous_message_id=500)
    assert not api.calls


def test_bot_handles_ministry_role_after_merge(env):
    _, factory, _, _ = env
    with factory() as db:
        user = db.scalar(select(User).where(User.email == "minsport@demo.example"))
        link = connect(db, user.id)
        for section in ("menu", "profile", "roles", "competitions", "deadlines"):
            body, keyboard = render(db, link, user, section, 0)
            assert body and keyboard
        body, _ = render(db, link, user, "applications", 0)
        assert "недоступен" in body
