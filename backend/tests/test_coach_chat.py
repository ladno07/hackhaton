from sqlalchemy import select
from app.models import AthleteCoach, Coach, CoachChatMessage, Notification, User
from app.security import Actor
from app.services.notifications import visible_in_role
from bot.delivery import deliver, notice_roles
from test_telegram import FakeTelegram, connect


def request_link(client, headers, users):
    response = client.post("/api/links", headers=headers["coach"], json={
        "athlete_id": users["athlete"]["athlete_id"], "discipline_id": 1})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_chat_requires_confirmation_and_participation(env):
    client, factory, headers, users = env
    link = request_link(client, headers, users)
    url = f"/api/links/{link}/messages"
    assert client.get(url, headers=headers["athlete"]).status_code == 409
    assert client.post(url, headers=headers["coach"], json={"body": "Рано"}).status_code == 409
    assert client.patch(f"/api/links/{link}", headers=headers["coach"], json={"status": "active"}).status_code == 403
    assert client.patch(f"/api/links/{link}", headers=headers["athlete"], json={"status": "active"}).status_code == 200
    for body in ("", "   ", "x" * 4001):
        assert client.post(url, headers=headers["coach"], json={"body": body}).status_code == 422
    sent = client.post(url, headers=headers["coach"], json={"body": " План тренировки "})
    assert sent.status_code == 201, sent.text
    assert sent.json()["body"] == "План тренировки"
    assert client.post(url, headers=headers["athlete"], json={"body": "Спасибо"}).status_code == 201
    assert [m["body"] for m in client.get(url, headers=headers["athlete"]).json()] == ["Спасибо", "План тренировки"]
    assert len(client.get(url, headers=headers["coach"], params={"before": sent.json()["id"] + 1}).json()) == 1
    for role in ("admin", "judge"):
        assert client.get(url, headers=headers[role]).status_code == 403
        assert client.post(url, headers=headers[role], json={"body": "Нет"}).status_code == 403
    with factory() as db:
        other = AthleteCoach(athlete_id=users["athlete"]["athlete_id"], coach_id=2, discipline_id=1, status="active")
        # Use another existing coach card if present, otherwise create one for another user.
        if not db.get(Coach, 2):
            db.add(Coach(id=2, user_id=users["judge"]["id"]))
        db.add(other)
        db.commit()
        other_id = other.id
    assert client.get(f"/api/links/{other_id}/messages", headers=headers["coach"]).status_code == 403
    assert client.post(f"/api/links/{other_id}/messages", headers=headers["coach"], json={"body": "Нет"}).status_code == 403
    assert client.patch(f"/api/links/{link}", headers=headers["athlete"], json={"status": "paused"}).status_code == 200
    assert client.get(url, headers=headers["coach"]).status_code == 409
    assert client.post(url, headers=headers["athlete"], json={"body": "Нет"}).status_code == 409
    client.patch(f"/api/links/{link}", headers=headers["athlete"], json={"status": "active"})
    assert len(client.get(url, headers=headers["coach"]).json()) == 2


def test_telegram_chat_goes_only_to_athlete(env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_bot_username", "fsp_test_bot")
    client, factory, headers, users = env
    link = request_link(client, headers, users)
    client.patch(f"/api/links/{link}", headers=headers["athlete"], json={"status": "active"})
    with factory() as db:
        connect(db, users["athlete"]["id"], 101)
        connect(db, users["coach"]["id"], 102)
    url = f"/api/links/{link}/messages"
    client.post(url, headers=headers["coach"], json={"body": "План тренировки"})
    client.post(url, headers=headers["athlete"], json={"body": "Ответ спортсмена"})
    api = FakeTelegram()
    with factory() as db:
        notices = db.scalars(select(Notification).where(Notification.event_key.like("coach-chat:%"))).all()
        assert len(notices) == 2
        for notice in notices:
            athlete_notice = notice.user_id == users["athlete"]["id"]
            assert notice_roles(db, notice, {}) == ({"athlete"} if athlete_notice else set())
            assert not visible_in_role(db, Actor(db.get(User, users["admin"]["id"]), "admin"), notice)
        deliver(db, api)
        assert len(api.messages) == 1
        assert api.messages[0][0] == 101
        assert "План тренировки" in api.messages[0][1]
        assert f"chat={link}" in str(api.messages[0][2])
        deliver(db, api)
        assert len(api.messages) == 1
    client.post(url, headers=headers["coach"], json={"body": "Уже неактуальное сообщение"})
    client.patch(f"/api/links/{link}", headers=headers["athlete"], json={"status": "ended"})
    with factory() as db:
        deliver(db, api)
        assert not any("Уже неактуальное" in m[1] for m in api.messages)
        assert len(db.scalars(select(CoachChatMessage)).all()) == 3


def test_link_changes_use_readable_messages_on_site_and_telegram(env, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_bot_username", "fsp_test_bot")
    client, factory, headers, users = env
    link = request_link(client, headers, users)
    with factory() as db:
        connect(db, users["athlete"]["id"], 101)
        connect(db, users["coach"]["id"], 102)
    api = FakeTelegram()
    for status, title in (("active", "Связь подтверждена"), ("paused", "Связь приостановлена"),
                          ("ended", "Связь завершена")):
        response = client.patch(f"/api/links/{link}", headers=headers["athlete"], json={"status": status})
        assert response.status_code == 200
        for role in ("athlete", "coach"):
            notices = client.get("/api/notifications", headers=headers[role]).json()
            notice = next(n for n in notices if n["event_key"].startswith(f"link-change:{link}:") and n["title"] == title)
            counterpart = "athlete" if role == "coach" else "coach"
            assert users[counterpart]["full_name"] in notice["body"]
            assert users[role]["full_name"] not in notice["body"]
            assert "Направление:" in notice["body"]
            assert not {"active", "paused", "ended"}.intersection(notice["body"].splitlines())
        with factory() as db:
            deliver(db, api)
        assert title in api.messages[-1][1]
        assert api.messages[-1][0] == 101
        assert users["coach"]["full_name"] in api.messages[-1][1]
        assert users["athlete"]["full_name"] not in api.messages[-1][1]
    assert len(api.messages) == 3
