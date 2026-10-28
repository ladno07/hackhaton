from datetime import date, timedelta
from sqlalchemy import select
import pytest
from app.models import Athlete, Coach, CoachDiscipline, GroupEnrollment, LessonAttendance
from app.services.standards import STAGES
from test_ministry import ministry_login


def setup_group(env, name="Тестовая группа", capacity=20):
    client, factory, h, users = env
    with factory() as db:
        athlete = db.get(Athlete, users["athlete"]["athlete_id"])
        coach = db.get(Coach, users["coach"]["coach_id"])
        athlete.training_stage = STAGES["ut"]
        org_id, coach_id = coach.organization_id, coach.id
        if not db.get(CoachDiscipline, (coach.id, 1)):
            db.add(CoachDiscipline(coach_id=coach.id, discipline_id=1))
        db.commit()
    org = next(o for o in client.get("/api/metadata", headers=h["admin"]).json()["organizations"] if o["id"] == org_id)
    org["programs"] = ["Алгоритмы: учебно-тренировочная программа"]
    org["license_number"] = "ДЕМО-001"
    org["license_valid_until"] = None
    body = {k: v for k, v in org.items() if k != "id"}
    res = client.put(f"/api/organizations/{org_id}", headers=h["admin"], json=body)
    assert res.status_code == 200, res.text
    res = client.post("/api/training-groups", headers=h["admin"], json={
        "name": name, "organization_id": org_id, "coach_id": coach_id, "discipline_id": 1,
        "stage": "ut", "program": org["programs"][0], "capacity": capacity,
    })
    assert res.status_code == 201, res.text
    return res.json()


def enroll(client, h, users, group, start=None):
    res = client.post(f"/api/training-groups/{group['id']}/enrollments", headers=h["admin"], json={
        "athlete_public_id": f"fsp-{users['athlete']['athlete_id']:06d}",
        "start_date": (start or date.today() - timedelta(days=2)).isoformat(), "order_number": "УТ-1",
    })
    assert res.status_code == 201, res.text
    return res.json()


def test_training_full_cycle_and_dynamics(env):
    client, factory, h, users = env
    group = setup_group(env)
    enrollment = enroll(client, h, users, group)
    gid = group["id"]
    assert client.get("/api/training-groups", headers=h["athlete"]).json()[0]["id"] == gid
    res = client.post(f"/api/training-groups/{gid}/lessons", headers=h["coach"], json={
        "held_on": (date.today() - timedelta(days=1)).isoformat(), "topic": "Разбор алгоритмов", "duration_minutes": 90,
    })
    assert res.status_code == 201, res.text
    a = client.get(f"/api/training-groups/{gid}/lessons", headers=h["athlete"]).json()[0]["attendance"][0]
    url = f"/api/lesson-attendance/{a['id']}"
    assert client.post(url + "/confirm", headers=h["athlete"]).status_code == 409
    assert client.patch(url, headers=h["coach"], json={"status": "present"}).status_code == 200
    assert client.post(url + "/confirm", headers=h["athlete"]).status_code == 200
    assert client.post(url + "/confirm", headers=h["athlete"]).status_code == 200
    assert client.patch(url, headers=h["coach"], json={"status": "absent"}).status_code == 409
    data = client.get("/api/reports/population", headers=h["admin"]).json()["training"]
    assert data["rows"][0][-4:] == [1, 1, 1, 1.5]
    assert data["rows"][0][-5] == 1
    ministry = ministry_login(client)
    assert client.get(f"/api/training-groups/{gid}", headers=ministry).status_code == 200
    assert client.patch(url, headers=ministry, json={"status": "absent"}).status_code == 403
    for fmt in ("pdf", "docx", "xlsx"):
        assert client.get(f"/api/exports/training-groups/{gid}.{fmt}", headers=h["coach"]).status_code == 200
        assert client.get(f"/api/exports/training-dynamics.{fmt}", headers=ministry).status_code == 200
    target = setup_group(env, "Вторая группа")
    res = client.post(f"/api/group-enrollments/{enrollment['id']}/transfer", headers=h["admin"], json={
        "target_group_id": target["id"], "on": date.today().isoformat(), "order_number": "П-2",
    })
    assert res.status_code == 201, res.text
    old = client.get(f"/api/training-groups/{gid}", headers=h["admin"]).json()
    assert old["enrollments"][0]["end_date"] == (date.today() - timedelta(days=1)).isoformat()
    assert old["enrollments"][0]["end_order_number"] == "П-2"
    assert client.post(f"/api/training-groups/{gid}/archive", headers=h["admin"]).status_code == 200
    with factory() as db:
        assert len(db.scalars(select(GroupEnrollment)).all()) == 2
        assert db.get(LessonAttendance, a["id"]).confirmed_at is not None


def test_training_scope_and_history_protection(env):
    client, _, h, users = env
    group = setup_group(env, capacity=1)
    gid = group["id"]
    assert client.get(f"/api/training-groups/{gid}", headers=h["athlete"]).status_code == 403
    assert client.get(f"/api/training-groups/{gid}", headers=h["judge"]).status_code == 403
    obj = enroll(client, h, users, group)
    assert client.post(f"/api/training-groups/{gid}/archive", headers=h["admin"]).status_code == 409
    body = {"held_on": (date.today() - timedelta(days=1)).isoformat(), "topic": "Тренировка", "duration_minutes": 60}
    assert client.post(f"/api/training-groups/{gid}/lessons", headers=h["athlete"], json=body).status_code == 403
    other_coach = {**h["admin"], "X-Active-Role": "coach"}
    assert client.post(f"/api/training-groups/{gid}/lessons", headers=other_coach, json=body).status_code == 403
    assert client.post(f"/api/training-groups/{gid}/lessons", headers=h["coach"], json=body).status_code == 201
    attendance = client.get(f"/api/training-groups/{gid}/lessons", headers=h["coach"]).json()[0]["attendance"][0]
    unrelated = {**h["admin"], "X-Active-Role": "athlete"}
    assert client.post(f"/api/lesson-attendance/{attendance['id']}/confirm", headers=unrelated).status_code == 403
    assert client.post(f"/api/group-enrollments/{obj['id']}/end", headers=h["admin"], json={
        "on": (date.today() - timedelta(days=2)).isoformat(), "order_number": "О-1",
    }).status_code == 409
    detail = client.get(f"/api/training-groups/{gid}", headers=h["admin"]).json()
    assert detail["enrollments"][0]["end_date"] is None


@pytest.mark.parametrize("changes, code", [
    ({"athlete_public_id": "123"}, 422),
    ({"athlete_public_id": "FSP-999999"}, 404),
    ({"start_date": (date.today() + timedelta(days=1)).isoformat()}, 422),
])
def test_enrollment_invalid_input(env, changes, code):
    client, _, h, users = env
    group = setup_group(env)
    body = {"athlete_public_id": f"FSP-{users['athlete']['athlete_id']:06d}", "start_date": date.today().isoformat(), "order_number": "1"}
    assert client.post(f"/api/training-groups/{group['id']}/enrollments", headers=h["admin"], json={**body, **changes}).status_code == code


def test_transfer_failure_rolls_back_and_stage_is_not_bypassed(env):
    client, factory, h, users = env
    group = setup_group(env)
    obj = enroll(client, h, users, group)
    target = setup_group(env, "ССМ")
    with factory() as db:
        from app.models import TrainingGroup
        db.get(TrainingGroup, target["id"]).stage = "ssm"
        db.commit()
    res = client.post(f"/api/group-enrollments/{obj['id']}/transfer", headers=h["admin"], json={
        "target_group_id": target["id"], "on": date.today().isoformat(), "order_number": "П-2",
    })
    assert res.status_code == 409
    assert client.get(f"/api/training-groups/{group['id']}", headers=h["admin"]).json()["enrollments"][0]["end_date"] is None


def test_duplicate_capacity_and_group_configuration(env):
    client, factory, h, users = env
    group = setup_group(env, capacity=1)
    enroll(client, h, users, group)
    url = f"/api/training-groups/{group['id']}"
    payload = {k: group[k] for k in ("organization_id", "discipline_id", "coach_id", "name", "stage", "program", "capacity")}
    assert client.put(url, headers=h["admin"], json={**payload, "stage": "np"}).status_code == 409
    assert client.post("/api/training-groups", headers=h["coach"], json=payload).status_code == 403
    assert client.post(url + "/enrollments", headers=h["admin"], json={
        "athlete_public_id": f"FSP-{users['athlete']['athlete_id']:06d}", "start_date": date.today().isoformat(), "order_number": "2",
    }).status_code == 409
    with factory() as db:
        other = db.scalars(select(Athlete).where(Athlete.id != users["athlete"]["athlete_id"], Athlete.organization_id == group["organization_id"])).first()
        other.training_stage = STAGES["ut"]
        other_id = other.id
        db.commit()
    assert client.post(url + "/enrollments", headers=h["admin"], json={
        "athlete_public_id": f"FSP-{other_id:06d}", "start_date": date.today().isoformat(), "order_number": "2",
    }).status_code == 409
    org = next(o for o in client.get("/api/metadata", headers=h["admin"]).json()["organizations"] if o["id"] == group["organization_id"])
    body = {k: v for k, v in org.items() if k != "id"}
    assert client.put(f"/api/organizations/{org['id']}", headers=h["admin"], json={**body, "programs": []}).status_code == 409


def test_cross_organization_transfer_updates_history_and_reports(env):
    client, factory, h, users = env
    group = setup_group(env)
    obj = enroll(client, h, users, group)
    from app.models import TrainingGroup, Organization, AthleteOrganization
    with factory() as db:
        org = db.scalars(select(Organization).where(Organization.id != group["organization_id"])).first()
        coach = db.get(Coach, users["coach"]["coach_id"])
        coach.organization_id = org.id
        org.programs = ["Алгоритмы"]
        db.commit()
        org_id = org.id
    target_body = {"name": "Новая организация", "organization_id": org_id, "coach_id": users["coach"]["coach_id"],
                   "discipline_id": 1, "stage": "ut", "program": "Алгоритмы", "capacity": 20}
    target = client.post("/api/training-groups", headers=h["admin"], json=target_body)
    assert target.status_code == 201, target.text
    result = client.post(f"/api/group-enrollments/{obj['id']}/transfer", headers=h["admin"], json={
        "target_group_id": target.json()["id"], "on": date.today().isoformat(), "order_number": "П-3",
    })
    assert result.status_code == 201, result.text
    with factory() as db:
        assert db.get(Athlete, users["athlete"]["athlete_id"]).organization_id == org_id
        current = db.scalars(select(AthleteOrganization).where(AthleteOrganization.athlete_id == users["athlete"]["athlete_id"], AthleteOrganization.end_date.is_(None))).one()
        assert current.organization_id == org_id and current.start_date == date.today()
    report = client.get(f"/api/reports/population?organization_id={org_id}", headers=h["admin"]).json()["training"]
    assert len(report["rows"]) == 1 and report["rows"][0][5] == 1


def test_profile_transfer_cannot_rewrite_closed_group_history(env):
    from fastapi import HTTPException
    from app.models import Organization
    from app.services.common import transfer
    client, factory, h, users = env
    group = setup_group(env)
    obj = enroll(client, h, users, group)
    yesterday = date.today() - timedelta(days=1)
    assert client.post(f"/api/group-enrollments/{obj['id']}/end", headers=h["admin"], json={
        "on": yesterday.isoformat(), "order_number": "О-1",
    }).status_code == 200
    with factory() as db:
        athlete = db.get(Athlete, users["athlete"]["athlete_id"])
        other_org = db.scalars(select(Organization).where(Organization.id != athlete.organization_id)).first()
        with pytest.raises(HTTPException) as error:
            transfer(db, athlete, other_org.id, yesterday)
        assert error.value.status_code == 409
