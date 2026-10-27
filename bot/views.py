"""Read-only bot views, always evaluated against the current user and role."""
from sqlalchemy import select
from fastapi import HTTPException
from app.models import Athlete, Competition, CompetitionApplication, CompetitionResult, Discipline, RankApplication
from app.security import Actor
from app.services.common import can_athlete
from app.routers.federation import list_deadlines, rank_applications
from app.routers.competitions import assignments
from bot.schedule import roles_for
from app.config import settings
from urllib.parse import urlsplit, urlunsplit
from bot.profile import profile_text

ROLE_NAMES = {"athlete": "Спортсмен", "coach": "Тренер", "judge": "Судья", "admin": "Федерация"}
STATUS = {"pending": "На рассмотрении", "approved": "Одобрено", "rejected": "Отклонено",
          "draft": "Черновик", "open": "Приём заявок", "closed": "Приём закрыт", "published": "Результаты"}
SECTIONS = {"profile": "Личный кабинет", "competitions": "Соревнования", "applications": "Мои заявки",
            "deadlines": "Мои сроки", "assignments": "Мои назначения", "logout": "Выход из аккаунта",
            "roles": "Выбор роли"}


def url(path):
    target = urlsplit(settings.public_site_url.rstrip("/") + path)
    # Telegram rejects the localhost hostname in URL buttons; its IPv4 loopback is a valid URL.
    if target.hostname and target.hostname.lower() == "localhost":
        target = target._replace(netloc="127.0.0.1" + (f":{target.port}" if target.port else ""))
    return urlunsplit(target)


def button(text, data=None, path=None):
    if data:
        return {"text": text, "callback_data": data}
    return {"text": text, "url": url(path)}


def menu(role):
    names = [k for k in SECTIONS if k != "assignments" or role in ("admin", "judge")]
    return [[button(SECTIONS[k], f"view:{k}:0")] for k in names]


def allowed_athlete(db, actor, athlete_id, discipline_id):
    try:
        can_athlete(db, actor, athlete_id, discipline_id)
        return True
    except HTTPException:
        return False


def render(db, link, user, section, page):
    roles = roles_for(db, user.id)
    if link.role not in roles:
        link.role = sorted(roles)[0] if roles else ""
    actor = Actor(user, link.role)
    if not roles:
        return "Нет доступных кабинетов. Обратитесь в федерацию.", []
    if section == "roles":
        return "Выберите роль. На сайте кабинет не изменится.", [
            *[[button(ROLE_NAMES[r], f"role:{r}")] for r in sorted(roles)],
            [button("Меню", "view:menu:0")]]
    if section == "profile":
        return profile_text(db, user, link.role, ROLE_NAMES), [[button("Меню", "view:menu:0")]]
    if section in {"settings", "logout"}:
        return "Выберите раздел.", menu(link.role)
    if section not in SECTIONS:
        return f"Кабинет: {ROLE_NAMES[link.role]}", menu(link.role)
    items = []
    if section == "competitions":
        query = select(Competition).order_by(Competition.start_date.desc(), Competition.id.desc())
        if actor.role != "admin":
            query = query.where(Competition.state != "draft")
        for c in db.scalars(query):
            discipline = db.get(Discipline, c.discipline_id)
            start_time = c.start_time.strftime("%H:%M") if c.start_time else "время уточняется"
            fmt = {"onsite": "Очно", "online": "Онлайн", "hybrid": "Смешанный"}[c.format]
            items.append((f"{c.title}\n{discipline.short_name} · {STATUS[c.state]}\n"
                          f"{c.start_date} — {c.end_date}, {start_time} ({c.timezone})\n{c.location} · {fmt}",
                          f"/competitions/{c.id}"))
    elif section == "applications":
        for app in db.scalars(select(CompetitionApplication).order_by(CompetitionApplication.id.desc())):
            c = db.get(Competition, app.competition_id)
            if allowed_athlete(db, actor, app.athlete_id, c.discipline_id):
                athlete = db.get(Athlete, app.athlete_id)
                items.append((f"{c.title}\n{athlete.user.full_name}: {STATUS[app.status]}\n{app.comment or ''}",
                              f"/competitions/{c.id}"))
        for app in rank_applications(actor=actor, db=db):
            if app["athlete_id"]:
                result = db.get(CompetitionResult, app["result_id"])
                comp = db.get(Competition, result.competition_id) if result else None
                if not comp or not allowed_athlete(db, actor, app["athlete_id"], comp.discipline_id):
                    continue
            items.append((f"{app['full_name']}: {app['name']}\n{STATUS[app['status']]}\n{app['comment'] or ''}", "/ranks"))
    elif section == "deadlines":
        for item in list_deadlines(actor=actor, db=db):
            if item["kind"] == "rank":
                from app.models import SportsRank
                rank = db.get(SportsRank, item["id"])
                if not allowed_athlete(db, actor, rank.athlete_id, rank.discipline_id):
                    continue
            path = f"/competitions/{item['id']}" if item["kind"] == "competition" else "/deadlines"
            items.append((f"{item['title']}\nСрок: {item['due_on']}", path))
    elif section == "assignments":
        if actor.role not in ("admin", "judge"):
            return "Этот раздел доступен судьям и федерации.", menu(link.role)
        for item in assignments(actor=actor, db=db):
            items.append((f"{item['title']}\n{item['position']} · {item['start_date']}",
                          f"/competitions/{item['competition_id']}"))
    page = min(max(0, page), max(0, (len(items) - 1) // 5))
    chunk = items[page * 5:page * 5 + 5]
    text = f"{SECTIONS[section]} · {ROLE_NAMES[link.role]}\nСтраница {page + 1}\n\n"
    keyboard = []
    for i, (body, path) in enumerate(chunk, 1):
        text += f"{i}. {body[:600]}\n\n"
        label = body.split("\n", 1)[0][:55]
        keyboard.append([button(f"↗ {label}", path=path)])
    if not chunk:
        text += "Записей пока нет."
    navigation = []
    if page:
        navigation.append(button("← Назад", f"view:{section}:{page - 1}"))
    if (page + 1) * 5 < len(items):
        navigation.append(button("Далее →", f"view:{section}:{page + 1}"))
    if navigation:
        keyboard.append(navigation)
    keyboard.append([button("Меню", "view:menu:0")])
    return text, keyboard
