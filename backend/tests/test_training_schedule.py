from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
import pytest
from app.models import Athlete, GroupEnrollment, LessonAttendance, Notification, TrainingLesson
from app.services.training_schedule import reminders
from test_training import setup_group, enroll


def planned(client, h, group, **overrides):
    body = {"held_on": (date.today() + timedelta(days=1)).isoformat(), "start_time": "18:00",
            "timezone": "Asia/Yekaterinburg", "duration_minutes": 90, "topic": "Практика алгоритмов",
            "format": "online", "meeting_url": "https://meet.example.org/training", "instructions": "Подготовьте ноутбук и решения задач."}
    body.update(overrides)
    res = client.post(f"/api/training-groups/{group['id']}/lessons", headers=h["coach"], json=body)
    assert res.status_code == 201, res.text
    return res.json(), body


def test_athlete_sees_when_where_and_role_scoped_notices(env):
    client, factory, h, users = env
    group = setup_group(env)
    enroll(client, h, users, group)
    lesson, _ = planned(client, h, group)
    assert lesson["status"] == "planned" and lesson["phase"] == "upcoming"
    assert lesson["starts_at"].startswith(lesson["held_on"] + "T13:00")
    agenda = client.get("/api/training-schedule", headers=h["athlete"]).json()
    assert len(agenda) == 1
    assert agenda[0]["meeting_url"] == "https://meet.example.org/training"
    assert agenda[0]["instructions"] == "Подготовьте ноутбук и решения задач."
    assert agenda[0]["attendance"] == []
    unrelated = {**h["admin"], "X-Active-Role": "athlete"}
    assert client.get("/api/training-schedule", headers=unrelated).json() == []
    notices = client.get("/api/notifications", headers=h["athlete"]).json()
    notice = next(n for n in notices if n["event_key"].startswith(f"training-lesson:{lesson['id']}:"))
    assert notice["telegram_context"]["path"] == f"/training?group={group['id']}"
    assert "18:00" in notice["body"] and "Asia/Yekaterinburg" in notice["body"]
    assert client.get("/api/training-schedule", headers=h["judge"]).status_code == 403
    assert client.post(f"/api/training-lessons/{lesson['id']}/complete", headers=h["coach"]).status_code == 409
    with factory() as db:
        assert not db.scalars(select(LessonAttendance).where(LessonAttendance.lesson_id == lesson["id"])).all()


@pytest.mark.parametrize("changes", [
    {"start_time": None}, {"meeting_url": None}, {"meeting_url": "javascript:alert(1)"},
    {"timezone": "Wrong/Zone"}, {"format": "onsite", "meeting_url": None, "location": ""},
])
def test_future_lesson_requires_actionable_details(env, changes):
    client, _, h, users = env
    group = setup_group(env)
    enroll(client, h, users, group)
    body = {"held_on": (date.today() + timedelta(days=1)).isoformat(), "start_time": "18:00", "duration_minutes": 60,
            "topic": "Тренировка", "format": "online", "meeting_url": "https://meet.example.org"}
    assert client.post(f"/api/training-groups/{group['id']}/lessons", headers=h["coach"], json={**body, **changes}).status_code == 422


def test_reschedule_conflicts_cancel_and_stale_notification(env):
    client, _, h, users = env
    group = setup_group(env)
    enroll(client, h, users, group)
    first, body = planned(client, h, group)
    second, _ = planned(client, h, group, start_time="20:00")
    # Moscow 16:00 equals Yekaterinburg 18:00: compare real instants, not wall time.
    res = client.put(f"/api/training-lessons/{second['id']}", headers=h["coach"], json={**body, "timezone": "Europe/Moscow", "start_time": "16:00"})
    assert res.status_code == 409, res.text
    after = client.get("/api/training-schedule", headers=h["athlete"]).json()
    assert next(l for l in after if l["id"] == second["id"])["start_time"].startswith("20:00")
    res = client.put(f"/api/training-lessons/{first['id']}", headers=h["coach"], json={**body, "start_time": "16:00", "format": "onsite", "meeting_url": None, "location": "Оренбург, учебный класс 12"})
    assert res.status_code == 200 and res.json()["revision"] == 2
    notices = client.get("/api/notifications", headers=h["athlete"]).json()
    assert not any(n["event_key"] == f"training-lesson:{first['id']}:1:planned" for n in notices)
    assert any(n["event_key"] == f"training-lesson:{first['id']}:2:rescheduled" for n in notices)
    assert client.post(f"/api/training-lessons/{first['id']}/cancel", headers=h["coach"], json={"reason": "Тренер заболел"}).status_code == 200
    assert all(l["id"] != first["id"] for l in client.get("/api/training-schedule", headers=h["athlete"]).json())
    assert client.post(f"/api/training-lessons/{first['id']}/complete", headers=h["coach"]).status_code == 409
    assert client.post(f"/api/training-lessons/{second['id']}/cancel", headers=h["athlete"], json={"reason": "Не могу"}).status_code == 403


def test_complete_mark_dispute_correct_and_confirm(env):
    client, factory, h, users = env
    group = setup_group(env)
    enroll(client, h, users, group)
    lesson, _ = planned(client, h, group, held_on=(date.today() - timedelta(days=1)).isoformat(), start_time="12:00")
    assert client.post(f"/api/training-lessons/{lesson['id']}/complete", headers=h["coach"]).status_code == 200
    assert client.post(f"/api/training-lessons/{lesson['id']}/complete", headers=h["coach"]).status_code == 409
    records = client.get(f"/api/training-groups/{group['id']}/lessons", headers=h["athlete"]).json()
    a = records[0]["attendance"][0]
    url = f"/api/lesson-attendance/{a['id']}"
    assert client.patch(url, headers=h["coach"], json={"status": "absent"}).status_code == 200
    assert client.post(url + "/dispute", headers=h["athlete"], json={"reason": "Я присутствовал на всём занятии"}).status_code == 200
    assert client.post(url + "/confirm", headers=h["athlete"]).status_code == 409
    coach_records = client.get(f"/api/training-groups/{group['id']}/lessons", headers=h["coach"]).json()
    assert coach_records[0]["attendance"][0]["dispute_reason"]
    assert any(n["event_key"].startswith("training-dispute:") for n in client.get("/api/notifications", headers=h["coach"]).json())
    assert client.patch(url, headers=h["coach"], json={"status": "present"}).status_code == 200
    assert client.post(url + "/confirm", headers=h["athlete"]).status_code == 200
    assert client.post(url + "/dispute", headers=h["athlete"], json={"reason": "Изменение"}).status_code == 409
    data = client.get("/api/reports/population", headers=h["admin"]).json()["training"]
    assert data["rows"][0][-4:] == [1, 1, 1, 1.5]


def test_ending_enrollment_removes_future_schedule_but_keeps_history(env):
    client, _, h, users = env
    group = setup_group(env)
    enrollment = enroll(client, h, users, group)
    planned(client, h, group)
    assert client.post(f"/api/group-enrollments/{enrollment['id']}/end", headers=h["admin"], json={"on": date.today().isoformat(), "order_number": "О-2"}).status_code == 200
    assert client.get("/api/training-schedule", headers=h["athlete"]).json() == []
    assert client.get(f"/api/training-groups/{group['id']}/lessons", headers=h["athlete"]).json() == []


def test_reminder_is_deduplicated_and_cancelled_lesson_is_silent(env, monkeypatch):
    client, factory, h, users = env
    group = setup_group(env)
    enroll(client, h, users, group)
    lesson, _ = planned(client, h, group)
    moment = datetime.fromisoformat(lesson["starts_at"].replace("Z", "+00:00")) - timedelta(minutes=45)
    monkeypatch.setattr("app.services.training_schedule.now", lambda: moment)
    with factory() as db:
        reminders(db)
        reminders(db)
        db.commit()
        key = f"training-lesson:{lesson['id']}:1:reminder"
        recipients = db.scalars(select(Notification).where(Notification.event_key == key)).all()
        assert len(recipients) == 2
    assert client.post(f"/api/training-lessons/{lesson['id']}/cancel", headers=h["coach"], json={"reason": "Отмена тренировки"}).status_code == 200
    with factory() as db:
        reminders(db)
        db.commit()
        assert len(db.scalars(select(Notification).where(Notification.event_key.endswith(":reminder"))).all()) == 2
