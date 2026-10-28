from datetime import date, timedelta
from sqlalchemy import select
import pytest
from app.models import LessonAttendance, TrainingMaterial
from test_training import setup_group, enroll
from test_ministry import ministry_login


def assignment(env, **changes):
    client, _, h, users = env
    group = setup_group(env)
    enrollment = enroll(client, h, users, group)
    data = {"held_on": date.today().isoformat(), "topic": "Самостоятельная работа: графы",
            "duration_minutes": 60, "format": "correspondence", "due_on": (date.today() + timedelta(days=7)).isoformat(),
            "instructions": "Изучите файл и решите задачи по приложенной ссылке."}
    data.update(changes)
    response = client.post(f"/api/training-groups/{group['id']}/lessons", headers=h["coach"], json=data)
    assert response.status_code == 201, response.text
    return group, enrollment, response.json(), data


def test_correspondence_materials_visible_downloadable_and_survive_reschedule(env):
    client, factory, h, users = env
    group, _, lesson, body = assignment(env)
    lid = lesson["id"]
    assert lesson["phase"] == "self_study" and lesson["starts_at"] is None
    content = "Задача: реализуйте поиск в ширину.\n".encode()
    res = client.post(f"/api/training-lessons/{lid}/materials/files", headers=h["coach"],
                      files={"file": ("задачи.txt", content, "text/plain")}, data={"title": "Задание № 1"})
    assert res.status_code == 201, res.text
    file = res.json()
    assert "data" not in file and file["title"] == "Задание № 1" and file["filename"] == "задачи.txt"
    link = client.post(f"/api/training-lessons/{lid}/materials/links", headers=h["coach"], json={"title": "Тренировочные задачи", "url": "https://example.org/contest"})
    assert link.status_code == 201, link.text
    agenda = client.get("/api/training-schedule", headers=h["athlete"]).json()
    assert len(agenda[0]["materials"]) == 2
    assert "data" not in agenda[0]["materials"][0]
    url = f"/api/training-materials/{file['id']}/download"
    download = client.get(url, headers=h["athlete"])
    assert download.status_code == 200 and download.content == content
    assert "attachment" in download.headers["content-disposition"]
    assert "filename*=UTF-8''" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"
    updated = client.put(f"/api/training-lessons/{lid}", headers=h["coach"], json={**body, "due_on": (date.today() + timedelta(days=10)).isoformat()})
    assert updated.status_code == 200, updated.text
    assert client.get(url, headers=h["athlete"]).content == content
    assert client.post(f"/api/training-lessons/{lid}/complete", headers=h["coach"]).status_code == 200
    with factory() as db:
        assert db.scalars(select(LessonAttendance).where(LessonAttendance.lesson_id == lid)).all() == []
    assert client.get(url, headers=h["athlete"]).content == content
    report = client.get("/api/reports/population", headers=h["admin"]).json()["training"]
    assert report["rows"][0][-4:] == [0, 0, 0, 0]


def test_material_permissions_and_period_are_checked_on_direct_download(env):
    client, _, h, users = env
    _, enrollment, lesson, _ = assignment(env, held_on=(date.today() + timedelta(days=1)).isoformat())
    base = f"/api/training-lessons/{lesson['id']}/materials"
    res = client.post(base + "/files", headers=h["coach"], files={"file": ("task.py", b"print('task')", "text/plain")})
    assert res.status_code == 201, res.text
    url = f"/api/training-materials/{res.json()['id']}/download"
    unrelated = {**h["admin"], "X-Active-Role": "athlete"}
    other_coach = {**h["admin"], "X-Active-Role": "coach"}
    assert client.get(url, headers=unrelated).status_code == 403
    assert client.get(url, headers=other_coach).status_code == 403
    assert client.get(url, headers=h["judge"]).status_code == 403
    assert client.get(url).status_code in (401, 403)
    assert client.post(base + "/links", headers=h["athlete"], json={"title": "Чужая ссылка", "url": "https://example.org"}).status_code == 403
    ministry = ministry_login(client)
    assert client.get(url, headers=ministry).status_code == 200
    assert client.post(base + "/links", headers=ministry, json={"title": "Ссылка", "url": "https://example.org"}).status_code == 403
    assert client.get(base + "?include_removed=true", headers=h["athlete"]).status_code == 403
    assert client.post(f"/api/group-enrollments/{enrollment['id']}/end", headers=h["admin"], json={"on": date.today().isoformat(), "order_number": "О-3"}).status_code == 200
    assert client.get(url, headers=h["athlete"]).status_code == 403
    assert client.get(base, headers=h["athlete"]).status_code == 403


def test_removal_is_reversible_and_cancelled_lesson_is_read_only(env):
    client, factory, h, _ = env
    _, _, lesson, _ = assignment(env)
    base = f"/api/training-lessons/{lesson['id']}/materials"
    res = client.post(base + "/files", headers=h["coach"], files={"file": ("readme.md", b"# Task", "text/plain")})
    mid = res.json()["id"]
    url = f"/api/training-materials/{mid}"
    assert client.delete(url, headers=h["coach"]).status_code == 204
    assert client.get(base, headers=h["athlete"]).json() == []
    assert client.get(url + "/download", headers=h["athlete"]).status_code == 404
    with factory() as db:
        assert db.get(TrainingMaterial, mid).data == b"# Task"
    assert client.post(url + "/restore", headers=h["coach"]).status_code == 200
    assert client.get(url + "/download", headers=h["athlete"]).content == b"# Task"
    assert client.post(f"/api/training-lessons/{lesson['id']}/cancel", headers=h["coach"], json={"reason": "Задание перенесено"}).status_code == 200
    assert client.post(base + "/links", headers=h["coach"], json={"title": "Новая", "url": "https://example.org"}).status_code == 409
    assert client.get(url + "/download", headers=h["athlete"]).status_code == 200


@pytest.mark.parametrize("name, content, code", [("empty.txt", b"", 422), ("bad.pdf", b"not pdf", 422), ("bad.exe", b"MZ...", 422), ("binary.py", b"\xff\x00", 422), ("large.txt", b"x" * (10 * 1024 * 1024 + 1), 413)])
def test_file_validation(env, name, content, code):
    client, _, h, _ = env
    _, _, lesson, _ = assignment(env)
    assert client.post(f"/api/training-lessons/{lesson['id']}/materials/files", headers=h["coach"], files={"file": (name, content)}).status_code == code


def test_links_and_combined_material_limit(env):
    client, _, h, _ = env
    _, _, lesson, _ = assignment(env)
    base = f"/api/training-lessons/{lesson['id']}/materials"
    assert client.post(base + "/links", headers=h["coach"], json={"title": "Bad", "url": "javascript:alert(1)"}).status_code == 422
    for number in range(20):
        assert client.post(base + "/links", headers=h["coach"], json={"title": f"Ресурс {number}", "url": f"https://example.org/{number}"}).status_code == 201
    assert client.post(base + "/files", headers=h["coach"], files={"file": ("extra.txt", b"data")}).status_code == 409


def test_correspondence_requires_task_and_deadline(env):
    client, _, h, users = env
    group = setup_group(env)
    enroll(client, h, users, group)
    base = {"held_on": date.today().isoformat(), "format": "correspondence", "topic": "Заочное занятие", "duration_minutes": 60}
    url = f"/api/training-groups/{group['id']}/lessons"
    assert client.post(url, headers=h["coach"], json=base).status_code == 422
    assert client.post(url, headers=h["coach"], json={**base, "instructions": "Задание", "due_on": (date.today() - timedelta(days=1)).isoformat()}).status_code == 422
