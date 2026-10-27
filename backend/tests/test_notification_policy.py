from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models import (
    AgeGroup, AthleteCoach, Competition, CompetitionApplication, Deadline, JudgeCategory, Notification, SportsRank, TelegramDelivery, User,
)
from app.security import Actor
from app.services.notifications import deadlines, visible_in_role
from bot.delivery import deliver, notice_roles
from bot.schedule import current_reminders, schedule
from bot.views import menu, render
from test_telegram import FakeTelegram, bot_settings, connect, competition_at
from test_workflows import open_comp

REGION = ZoneInfo("Asia/Yekaterinburg")


def test_announcements_follow_profile_and_active_role(env):
    client, factory, headers, users = env
    matching = open_comp(client, headers["admin"])
    wrong_discipline = open_comp(client, headers["admin"], discipline_id=2)
    wrong_age = open_comp(client, headers["admin"], min_age=60, max_age=80)
    with factory() as db:
        athlete = db.get(User, users["athlete"]["id"])
        group = AgeGroup(name="Другая группа", sex="male" if athlete.sex != "male" else "female",
                         min_age=0, max_age=100, age_rule="year")
        db.add(group)
        db.commit()
        group_id = group.id
    wrong_sex = open_comp(client, headers["admin"], age_group_ids=[group_id])
    notices = client.get("/api/notifications", headers=headers["athlete"]).json()
    opened = {int(n["event_key"].split(":")[1]) for n in notices
              if n["event_key"].startswith("competition-open:")}
    assert matching["id"] in opened
    assert wrong_discipline["id"] not in opened
    assert wrong_age["id"] not in opened
    assert wrong_sex["id"] not in opened
    for role in ("admin", "coach", "judge"):
        assert not any(n["event_key"].startswith("competition-open:") for n in
                       client.get("/api/notifications", headers=headers[role]).json())
    with factory() as db:
        admin = db.get(User, users["admin"]["id"])
        notice = db.scalar(select(Notification).where(
            Notification.user_id == admin.id,
            Notification.event_key.like(f"competition-open:{matching['id']}:%")))
        assert notice is not None  # This account also has an athlete profile.
        assert not visible_in_role(db, Actor(admin, "admin"), notice)
        assert notice_roles(db, notice, {}) == {"athlete"}


def test_ending_deadline_requires_admission_and_is_only_for_athlete(env, monkeypatch):
    client, factory, headers, users = env
    comp = open_comp(client, headers["admin"], start_date=str(date.today()),
                     end_date=str(date.today() + timedelta(days=1)), deadline=str(date.today()))
    at = datetime.combine(date.today(), time(12), REGION)
    import app.services.competition_notifications as policy
    monkeypatch.setattr(policy, "now", lambda: at)
    with factory() as db:
        uid = users["athlete"]["id"]
        db.get(User, uid).created_at = at - timedelta(days=10)
        db.add(AthleteCoach(athlete_id=users["athlete"]["athlete_id"],
                           coach_id=users["coach"]["coach_id"], discipline_id=1, status="active"))
        db.flush()
        prefix = f"tg-reminder:end:{comp['id']}:"
        assert not any(r.user_id == uid and r.key.startswith(prefix) for r in current_reminders(db, at).values())
        application = CompetitionApplication(competition_id=comp["id"], athlete_id=users["athlete"]["athlete_id"],
                                             submitted_by=uid, status="pending")
        db.add(application)
        db.flush()
        assert not any(r.user_id == uid and r.key.startswith(prefix) for r in current_reminders(db, at).values())
        application.status, application.approved_at = "approved", at - timedelta(days=1)
        db.flush()
        reminders = [r for r in current_reminders(db, at).values() if r.key.startswith(prefix)]
        assert any(r.user_id == uid for r in reminders)
        assert all(r.roles == {"athlete"} for r in reminders)
        assert all(r.user_id != users["coach"]["id"] for r in reminders)
        deadlines(db)
        notices = db.scalars(select(Notification).where(
            Notification.event_key.like(f"deadline:end:{comp['id']}:%"))).all()
        assert any(n.user_id == uid for n in notices)
        assert all(n.user_id != users["coach"]["id"] for n in notices)
        application.status = "rejected"
        db.flush()
        assert not any(r.user_id == uid and r.key.startswith(prefix)
                       for r in current_reminders(db, at).values())


def test_late_connection_does_not_deliver_backfilled_reminder(env):
    start = date.today() + timedelta(days=8)
    comp = competition_at(env, start)
    _, factory, _, users = env
    end = start + timedelta(days=2)
    connected = datetime.combine(end - timedelta(days=1), time(12), REGION)
    api = FakeTelegram()
    with factory() as db:
        uid = users["athlete"]["id"]
        db.get(Competition, comp["id"]).end_date = end
        connect(db, uid, at=connected)
        # The scheduler first discovers this reminder after the connection.
        schedule(db, connected)
        db.commit()
        deliver(db, api, connected)
        assert not any("Соревнование завершается" in m[1] and comp["title"] in m[1] for m in api.messages)
        following = datetime.combine(end, time(9), REGION)
        schedule(db, following)
        db.commit()
        deliver(db, api, following)
        matching = [m for m in api.messages if "Соревнование завершается" in m[1] and comp["title"] in m[1]]
        assert len(matching) == 1
        deliver(db, api, following)
        assert len([m for m in api.messages if "Соревнование завершается" in m[1] and comp["title"] in m[1]]) == 1
        after = datetime.combine(end + timedelta(days=1), time(), REGION)
        assert not any(r.key.startswith(f"tg-reminder:end:{comp['id']}:") for r in current_reminders(db, after).values())
        db.get(Competition, comp["id"]).state = "published"
        db.flush()
        assert not any(r.key.startswith(f"tg-reminder:end:{comp['id']}:") for r in current_reminders(db, following).values())


def test_new_account_does_not_receive_past_ending_or_rank_stage(env):
    start = date.today() + timedelta(days=8)
    comp = competition_at(env, start)
    _, factory, _, users = env
    end = start + timedelta(days=2)
    registered = datetime.combine(end - timedelta(days=1), time(12), REGION)
    with factory() as db:
        uid = users["athlete"]["id"]
        db.get(User, uid).created_at = registered
        db.get(Competition, comp["id"]).end_date = end
        rank = db.scalar(select(SportsRank).where(SportsRank.athlete_id == users["athlete"]["athlete_id"]))
        rank.expires_on = registered.date() + timedelta(days=7)
        db.flush()
        keys = [r.key for r in current_reminders(db, registered).values() if r.user_id == uid]
        assert not any(k.startswith(f"tg-reminder:end:{comp['id']}:") for k in keys)
        assert not any(k.startswith(f"tg-reminder:rank:{rank.id}:") for k in keys)
        following = datetime.combine(end, time(9), REGION)
        assert any(r.user_id == uid and r.key.startswith(f"tg-reminder:end:{comp['id']}:")
                   for r in current_reminders(db, following).values())


def test_federation_menu_and_page_numbers(env):
    assert not any(b.get("callback_data") == "view:assignments:0" for row in menu("admin") for b in row)
    assert any(b.get("callback_data") == "view:assignments:0" for row in menu("judge") for b in row)
    _, factory, _, users = env
    with factory() as db:
        link = connect(db, users["admin"]["id"])
        link.role = "admin"
        user = db.get(User, link.user_id)
        body, _ = render(db, link, user, "competitions", 0)
        assert "Страница" not in body
        body, _ = render(db, link, user, "assignments", 0)
        assert "доступен судьям" in body


def test_role_menus_and_scoped_sections(env):
    _, factory, _, users = env
    labels = lambda role: [b["text"].split(" ", 1)[1] for row in menu(role) for b in row]
    assert "Мои спортсмены" in labels("coach") and "Разряды моих спортсменов" in labels("coach")
    assert not any(b.get("callback_data") == "view:applications:0" for row in menu("coach") for b in row)
    assert "Моя категория" not in labels("judge") and "Мои заявки" not in labels("judge")
    assert not any(b.get("callback_data") == "view:ranks:0" for row in menu("judge") for b in row)
    assert "Квалификации" in labels("admin") and "Отчётные сроки" in labels("admin")
    with factory() as db:
        link = connect(db, users["coach"]["id"])
        link.role = "coach"
        user = db.get(User, link.user_id)
        body, _ = render(db, link, user, "athletes", 0)
        assert "Мои спортсмены" in body
        denied, _ = render(db, link, user, "applications", 0)
        assert "недоступен" in denied
        assert users["athlete"]["full_name"] not in body  # This athlete is not linked to this coach.
        body, _ = render(db, link, user, "assignments", 0)
        assert "доступен судьям" in body
        assert not any("admin" in r.roles for r in current_reminders(db).values()
                       if r.key.startswith(("tg-reminder:rank:", "tg-reminder:category:")))
        link.role = "judge"
        judge = db.get(User, users["judge"]["id"])
        denied, _ = render(db, link, judge, "ranks", 0)
        assert "недоступен" in denied


def test_staff_notifications_visible_on_site_and_queued_telegram_cancelled(env):
    client, factory, headers, users = env
    api = FakeTelegram()
    with factory() as db:
        for chat, role in enumerate(("coach", "judge", "admin"), 201):
            link = connect(db, users[role]["id"], chat)
            notice = Notification(user_id=link.user_id, title="Старое уведомление",
                                  body="Не отправлять", event_key="test:staff",
                                  telegram_context={"roles": [role]})
            db.add(notice)
            db.flush()
            assert visible_in_role(db, Actor(db.get(User, link.user_id), role), notice)
            assert notice_roles(db, notice, {}) == set()
            db.commit()
            assert any(n["id"] == notice.id for n in client.get("/api/notifications", headers=headers[role]).json())
            assert client.patch(f"/api/notifications/{notice.id}/read", headers=headers[role]).status_code == 200
        deliver(db, api)
        assert not api.messages
        deliveries = db.scalars(select(TelegramDelivery)).all()
        assert len(deliveries) == 3
        assert all(d.status == "cancelled" for d in deliveries)


def test_two_column_menus_and_role_selection_with_logout_last(env, monkeypatch):
    for role in ("admin", "athlete", "coach", "judge"):
        keyboard = menu(role)
        assert keyboard[-1] == [{"text": "🚪 Выход из аккаунта", "callback_data": "view:logout:0"}]
        assert all(len(row) == 2 for row in keyboard[:-2])
        assert 1 <= len(keyboard[-2]) <= 2
    _, factory, _, users = env
    monkeypatch.setattr("bot.views.roles_for", lambda db, uid: {"admin", "athlete", "coach", "judge"})
    with factory() as db:
        link = connect(db, users["admin"]["id"])
        _, keyboard = render(db, link, db.get(User, link.user_id), "roles", 0)
        assert [len(row) for row in keyboard] == [2, 2, 1]
        assert [b["callback_data"] for row in keyboard for b in row] == [
            "role:admin", "role:athlete", "role:coach", "role:judge", "view:logout:0"]


def test_late_admission_does_not_replay_start_reminder(env):
    start = date.today() + timedelta(days=8)
    comp = competition_at(env, start)
    _, factory, _, users = env
    stage = datetime.combine(start - timedelta(days=3), time(9), REGION)
    with factory() as db:
        uid = users["athlete"]["id"]
        application = db.scalar(select(CompetitionApplication).where(
            CompetitionApplication.competition_id == comp["id"]))
        application.approved_at = stage + timedelta(hours=1)
        db.flush()
        assert not any(r.user_id == uid and r.key.startswith(f"tg-reminder:start:{comp['id']}:")
                       for r in current_reminders(db, stage + timedelta(hours=2)).values())
        following = datetime.combine(start, time(9), REGION)
        assert any(r.user_id == uid and r.key.startswith(f"tg-reminder:start:{comp['id']}:")
                   for r in current_reminders(db, following).values())


def test_site_deadlines_begin_after_approval(env):
    client, _, headers, users = env
    start = date.today() + timedelta(days=5)
    comp = open_comp(client, headers["admin"], start_date=str(start), end_date=str(start + timedelta(days=2)))
    application = client.post(f"/api/competitions/{comp['id']}/applications", headers=headers["athlete"],
                              json={"athlete_id": users["athlete"]["athlete_id"]}).json()
    before = client.get("/api/deadlines", headers=headers["athlete"]).json()
    assert not any(d["kind"].startswith("competition") and d["id"] == comp["id"] for d in before)
    decision = client.patch(f"/api/applications/{application['id']}", headers=headers["admin"], json={"status": "approved"})
    assert decision.status_code == 200 and decision.json()["approved_at"]
    after = client.get("/api/deadlines", headers=headers["athlete"]).json()
    assert {d["kind"] for d in after if d["id"] == comp["id"] and d["kind"].startswith("competition")} == {
        "competition_start", "competition_end"}
    federation = client.get("/api/deadlines", headers=headers["admin"]).json()
    assert all(d["kind"] in ("report", "governor") for d in federation)


def test_expiration_and_reporting_recipients_follow_role_policy(env):
    _, factory, _, users = env
    at = datetime.combine(date.today() + timedelta(days=2), time(9), REGION)
    with factory() as db:
        rank = db.scalar(select(SportsRank).where(SportsRank.athlete_id == users["athlete"]["athlete_id"]))
        rank.expires_on = at.date() + timedelta(days=30)
        category = db.scalar(select(JudgeCategory).where(JudgeCategory.judge_id == users["judge"]["judge_id"]))
        category.expires_on = at.date() + timedelta(days=30)
        db.add(Deadline(title="Отчёт для проверки", due_on=at.date() + timedelta(days=30)))
        db.flush()
        reminders = list(current_reminders(db, at).values())
        sports = [r for r in reminders if r.key.startswith(f"tg-reminder:rank:{rank.id}:")]
        judging = [r for r in reminders if r.key.startswith(f"tg-reminder:category:{category.id}:")]
        assert any(r.user_id == users["athlete"]["id"] for r in sports)
        assert not judging
        assert all(r.roles == {"athlete"} for r in reminders)
        assert not any(r.title == "Приближается срок отчёта" for r in reminders)


def test_legacy_registration_mail_is_suppressed_without_blocking_other_notices(env, monkeypatch):
    client, factory, headers, users = env
    comp = open_comp(client, headers["admin"])
    import app.services.notifications as notifications
    messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    with factory() as db:
        # Old versions broadcast registration to coaches. These must not be sent
        # after the policy changes or prevent later valid mail being delivered.
        db.add_all([Notification(user_id=users["coach"]["id"], title="Старый анонс",
                                 body="Не отправлять", event_key=f"competition-open:{comp['id']}:{i + 100}")
                    for i in range(60)])
        db.add(Notification(user_id=users["athlete"]["id"], title="Полезное событие",
                            body="Отправить", event_key="test:valid"))
        db.commit()
        notifications.deliver(db)
        assert not any(m["Subject"] == "Старый анонс" for m in messages)
        assert any(m["Subject"] == "Полезное событие" for m in messages)
