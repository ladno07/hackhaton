from datetime import date
from sqlalchemy import select
from app.models import *
from tests.test_workflows import open_comp


def test_ended_link_can_be_requested_again(env):
    client, _, h, u = env
    body = {"athlete_id": u["athlete"]["athlete_id"], "discipline_id": 1}
    lid = client.post("/api/links", headers=h["coach"], json=body).json()["id"]
    assert client.post("/api/links", headers=h["coach"], json=body).status_code == 409
    client.patch(f"/api/links/{lid}", headers=h["athlete"], json={"status": "ended"})
    again = client.post("/api/links", headers=h["coach"], json=body)
    assert again.status_code == 201, again.text
    assert again.json()["id"] == lid and again.json()["status"] == "pending"
    accepted = client.patch(
        f"/api/links/{lid}", headers=h["athlete"], json={"status": "active"}
    )
    assert accepted.status_code == 200, accepted.text
    link = next(
        x for x in client.get("/api/links", headers=h["athlete"]).json() if x["id"] == lid
    )
    assert [x["status"] for x in link["history"]] == ["pending", "ended", "pending", "active"]
    requests = [
        n for n in client.get("/api/notifications", headers=h["athlete"]).json()
        if n["title"] == "Запрос от тренера"
    ]
    assert len(requests) == 2


def test_judge_sees_participants_and_can_be_removed(env):
    client, _, h, u = env
    cid = open_comp(client, h["admin"])["id"]
    url = f"/api/competitions/{cid}/judges"
    judge = {"judge_id": u["judge"]["judge_id"], "position": "Главный судья"}
    assert client.post(url, headers=h["admin"], json=judge).status_code == 201
    apid = client.post(
        f"/api/competitions/{cid}/applications",
        headers=h["athlete"],
        json={"athlete_id": u["athlete"]["athlete_id"]},
    ).json()["id"]
    detail = lambda: client.get(f"/api/competitions/{cid}", headers=h["judge"]).json()
    # pending applications stay with the federation
    assert detail()["applications"] == []
    client.patch(f"/api/applications/{apid}", headers=h["admin"], json={"status": "approved"})
    assert [a["id"] for a in detail()["applications"]] == [apid]

    assert client.delete(f"{url}/999999", headers=h["admin"]).status_code == 404
    assert client.delete(f"{url}/{judge['judge_id']}", headers=h["judge"]).status_code == 403
    assert client.delete(f"{url}/{judge['judge_id']}", headers=h["admin"]).status_code == 204
    assert detail()["judges"] == [] and detail()["applications"] == []
    titles = [n["title"] for n in client.get("/api/notifications", headers=h["judge"]).json()]
    assert "Назначение на соревнование отменено" in titles
    # a reassignment is announced again
    assert client.post(url, headers=h["admin"], json=judge).status_code == 201
    titles = [n["title"] for n in client.get("/api/notifications", headers=h["judge"]).json()]
    assert titles.count("Назначение на соревнование") == 2


def test_login_without_roles_is_refused(env):
    client, factory, _, u = env
    with factory() as db:
        user = db.get(User, u["athlete"]["id"])
        user.roles = []
        db.commit()
    client.cookies.clear()
    res = client.post(
        "/api/auth/login",
        json={"email": "athlete@demo.example", "password": "DemoPass2026!"},
    )
    assert res.status_code == 403


def test_year_defaults_follow_today(env):
    client, _, h, _ = env
    year = date.today().year
    assert client.get("/api/ratings", headers=h["admin"]).status_code == 200
    assert client.get("/api/team", headers=h["admin"]).status_code == 200
    indicators = client.get("/api/indicators", headers=h["admin"]).json()
    assert indicators["years"] == [year - 2, year - 1, year]


def test_admin_with_ministry_logs_in_as_admin(env):
    client, factory, _, u = env
    with factory() as db:
        # ministry linked before admin, as PostgreSQL may return it after the demo seed
        db.query(UserRole).filter(UserRole.user_id == u["admin"]["id"]).delete()
        db.add(UserRole(user_id=u["admin"]["id"], role_id="ministry"))
        db.flush()
        db.add(UserRole(user_id=u["admin"]["id"], role_id="admin"))
        db.commit()
    client.cookies.clear()
    res = client.post(
        "/api/auth/login",
        json={"email": "admin@demo.example", "password": "DemoPass2026!"},
    )
    assert res.json()["user"]["roles"] == ["admin", "ministry"]
