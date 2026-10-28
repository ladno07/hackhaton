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


def test_draft_with_judges_can_be_deleted(env):
    client, factory, h, u = env
    from tests.test_workflows import competition

    comp = competition(client, h["admin"])
    judge_id = u["judge"]["judge_id"]
    res = client.post(f"/api/competitions/{comp['id']}/judges", headers=h["admin"],
                      json={"judge_id": judge_id, "position": "Главный судья"})
    assert res.status_code == 201, res.text
    res = client.delete(f"/api/competitions/{comp['id']}", headers=h["admin"])
    assert res.status_code == 204, res.text
    with factory() as db:
        assert db.get(Competition, comp["id"]) is None
        assert not db.scalars(select(CompetitionJudge).where(
            CompetitionJudge.competition_id == comp["id"])).all()
    keys = [n["event_key"] for n in client.get("/api/notifications", headers=h["judge"]).json()]
    assert any(k.startswith(f"judge-removed:{comp['id']}:{judge_id}:") for k in keys)


def mail_server(monkeypatch, refuse=(), down=False):
    """Fake SMTP: refuses the given recipients or the whole connection."""
    import smtplib
    import app.services.notifications as notifications
    sent = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            if down:
                raise ConnectionRefusedError("SMTP is down")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send_message(self, message):
            if message["To"] in refuse:
                raise smtplib.SMTPRecipientsRefused({message["To"]: (550, b"No such user")})
            sent.append(message["To"])

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    return sent


def test_refused_recipient_does_not_block_mail(env, monkeypatch):
    _, factory, _, u = env
    from app.services.notifications import MAX_MAIL_ATTEMPTS, deliver, notify

    with factory() as db:
        for notice in db.scalars(select(Notification)):
            notice.mailed_at = notice.created_at
        notify(db, [u["athlete"]["id"]], "Первое", "Адрес отклонён", "test:refused")
        notify(db, [u["coach"]["id"]], "Второе", "Должно уйти", "test:next")
        db.commit()
        refused = db.get(User, u["athlete"]["id"]).email
        bad = db.scalar(select(Notification).where(Notification.event_key == "test:refused"))

        # the server is down: nothing is lost, attempts are not spent
        assert mail_server(monkeypatch, down=True) == []
        deliver(db)
        assert bad.attempts == 0 and "down" in bad.last_error

        sent = mail_server(monkeypatch, refuse={refused})
        deliver(db)
        assert sent == [db.get(User, u["coach"]["id"]).email]
        assert bad.mailed_at is None and bad.attempts == 1
        for _ in range(MAX_MAIL_ATTEMPTS + 2):
            deliver(db)
        # retried a few times, then left behind
        assert bad.attempts == MAX_MAIL_ATTEMPTS and bad.mailed_at is None


def test_old_unsent_notices_are_not_mailed(env, monkeypatch):
    _, factory, _, u = env
    from datetime import timedelta
    from app.services.notifications import MAIL_WINDOW, deliver, notify

    with factory() as db:
        for notice in db.scalars(select(Notification)):
            notice.mailed_at = notice.created_at
        notify(db, [u["athlete"]["id"]], "Старое", "Не отправлять", "test:stale")
        stale = db.scalar(select(Notification).where(Notification.event_key == "test:stale"))
        stale.created_at = now() - MAIL_WINDOW - timedelta(hours=1)
        db.commit()
        sent = mail_server(monkeypatch)
        deliver(db)
        assert sent == [] and stale.mailed_at is None


def test_rank_and_end_reminders_are_not_duplicated_on_site(env):
    client, factory, h, u = env
    from datetime import timedelta
    from app.services.notifications import deadlines
    from bot.schedule import schedule

    with factory() as db:
        rank = db.scalar(select(SportsRank).where(SportsRank.athlete_id == u["athlete"]["athlete_id"]))
        rank.expires_on = date.today() + timedelta(days=6)
        user = db.get(User, u["athlete"]["id"])
        user.created_at = user.created_at - timedelta(days=60)
        db.commit()
        deadlines(db)
        current = schedule(db)
        db.commit()
        # the bot keeps its own copy for Telegram
        assert any(key.startswith(f"tg-reminder:rank:{rank.id}:") for _, key in current)
    keys = [n["event_key"] for n in client.get("/api/notifications", headers=h["athlete"]).json()]
    assert any(k.startswith(f"deadline:rank:{rank.id}:") for k in keys)
    assert not any(k.startswith(("tg-reminder:rank:", "tg-reminder:end:")) for k in keys)
