"""Read-only bot views, always evaluated against the current user and role."""
from sqlalchemy import select
from fastapi import HTTPException
from app.models import Athlete, AthleteCoach, Coach, Competition, CompetitionApplication, CompetitionResult, Discipline, SportsRank
from app.security import Actor
from app.services.common import can_athlete, visible_athletes, own
from app.routers.federation import list_deadlines, rank_applications, ranks
from app.routers.competitions import assignments
from bot.schedule import roles_for
from app.config import settings
from urllib.parse import urlsplit, urlunsplit
from bot.profile import profile_text

ROLE_NAMES = {"athlete": "Спортсмен", "coach": "Тренер", "judge": "Судья", "admin": "Федерация", "ministry": "Минспорт"}
STATUS = {"pending": "На рассмотрении", "approved": "Одобрено", "rejected": "Отклонено",
          "draft": "Черновик", "open": "Приём заявок", "closed": "Приём закрыт", "published": "Результаты"}
SECTIONS = {"profile": "Личный кабинет", "competitions": "Соревнования", "applications": "Мои заявки",
            "deadlines": "Мои сроки", "assignments": "Мои назначения", "roles": "Выбор роли",
            "logout": "Выход из аккаунта"}
SECTIONS.update({"athletes": "Мои спортсмены", "ranks": "Разряды и категории"})
ROLE_SECTIONS = {
    "athlete": ("profile", "competitions", "applications", "deadlines"),
    "coach": ("profile", "athletes", "competitions", "ranks"),
    "judge": ("profile", "assignments", "competitions"),
    "admin": ("profile", "applications", "ranks", "deadlines"),
    "ministry": ("profile", "competitions", "deadlines"),
}
ROLE_LABELS = {
    "coach": {"ranks": "Разряды моих спортсменов"},
    "admin": {"applications": "Заявки участников", "ranks": "Квалификации", "deadlines": "Отчётные сроки"},
}


def section_label(role, section):
    return ROLE_LABELS.get(role, {}).get(section, SECTIONS[section])


def url(path):
    target = urlsplit(settings.public_site_url.rstrip("/") + path)
    # Telegram rejects the localhost hostname in URL buttons; its IPv4 loopback is a valid URL.
    if target.hostname and target.hostname.lower() == "localhost":
        target = target._replace(netloc="127.0.0.1" + (f":{target.port}" if target.port else ""))
    return urlunsplit(target)


def button(text, data=None, path=None):
    icons = {
        "profile": "👤", "competitions": "🏆", "applications": "📝",
        "deadlines": "⏰", "assignments": "⚖️", "roles": "🔄",
        "logout": "🚪", "athletes": "🏃", "ranks": "🏅", "menu": "🏠",
    }
    role_icons = {"athlete": "🏃", "coach": "📣", "judge": "⚖️", "admin": "🏛️"}
    if data and data.startswith("view:"):
        icon = icons.get(data.split(":")[1], "📋")
        if text.startswith("←") or text.endswith("→"):
            icon = "⬅️" if text.startswith("←") else "➡️"
    elif data and data.startswith("role:"):
        icon = role_icons.get(data.split(":")[1], "👤")
    elif data and data.startswith("confirm:"):
        icon = "✅"
    else:
        icon = "🔗"
    text = f"{icon} {text}"
    if data:
        return {"text": text, "callback_data": data}
    return {"text": text, "url": url(path)}


def menu(role):
    names = (*ROLE_SECTIONS.get(role, ()), "roles")
    buttons = [button(section_label(role, k), f"view:{k}:0") for k in names]
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)] + [
        [button(SECTIONS["logout"], "view:logout:0")]]


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
        buttons = [button(ROLE_NAMES[r], f"role:{r}")
                   for r in ("admin", "athlete", "coach", "judge", "ministry") if r in roles]
        return "Выберите роль. На сайте кабинет не изменится.", [
            *[buttons[i:i + 2] for i in range(0, len(buttons), 2)],
            [button(SECTIONS["logout"], "view:logout:0")]]
    if section == "profile":
        return profile_text(db, user, link.role, ROLE_NAMES), [[button("Меню", "view:menu:0")]]
    if section in {"settings", "logout"}:
        return "Выберите раздел.", menu(link.role)
    if section not in SECTIONS:
        return f"Кабинет: {ROLE_NAMES[link.role]}", menu(link.role)
    if section == "assignments" and actor.role != "judge":
        return "Этот раздел доступен судьям.", menu(link.role)
    if section not in ROLE_SECTIONS.get(actor.role, ()):
        return "Этот раздел недоступен в выбранной роли.", menu(link.role)
    items = []
    if section == "athletes":
        coach = own(db, Coach, actor)
        for athlete in db.scalars(select(Athlete).where(Athlete.id.in_(visible_athletes(db, actor))).order_by(Athlete.id)):
            disciplines = db.scalars(select(Discipline).join(AthleteCoach, AthleteCoach.discipline_id == Discipline.id).where(
                AthleteCoach.athlete_id == athlete.id, AthleteCoach.coach_id == coach.id, AthleteCoach.status == "active")).all()
            items.append((f"{athlete.user.full_name}\nДисциплины: {', '.join(d.short_name for d in disciplines)}",
                          "/coaching"))
    elif section == "ranks":
        current = ranks(actor=actor, db=db)
        for rank in current["sports"]:
            record = db.get(SportsRank, rank["id"])
            if not allowed_athlete(db, actor, record.athlete_id, record.discipline_id):
                continue
            items.append((f"{rank['full_name']}: {rank['name']}\nДействует до {rank['expires_on']:%d.%m.%Y}", "/ranks"))
        for category in current["categories"]:
            items.append((f"{category['full_name']}: {category['name']}\nДействует до {category['expires_on']:%d.%m.%Y}", "/ranks"))
        for app in rank_applications(actor=actor, db=db):
            if app["athlete_id"]:
                result = db.get(CompetitionResult, app["result_id"])
                comp = db.get(Competition, result.competition_id) if result else None
                if not comp or not allowed_athlete(db, actor, app["athlete_id"], comp.discipline_id):
                    continue
            items.append((f"Заявка: {app['full_name']} · {app['name']}\n{STATUS[app['status']]}", "/ranks"))
    elif section == "competitions":
        query = select(Competition).order_by(Competition.start_date.desc(), Competition.id.desc())
        if actor.role != "admin":
            query = query.where(Competition.state != "draft")
        assigned_ids = {item["competition_id"] for item in assignments(actor=actor, db=db)} if actor.role == "judge" else set()
        for c in db.scalars(query):
            if actor.role == "judge" and c.id not in assigned_ids:
                continue
            if actor.role == "coach" and not any(
                allowed_athlete(db, actor, application.athlete_id, c.discipline_id)
                for application in db.scalars(select(CompetitionApplication).where(
                    CompetitionApplication.competition_id == c.id))):
                continue
            discipline = db.get(Discipline, c.discipline_id)
            start_time = c.start_time.strftime("%H:%M") if c.start_time else "время уточняется"
            fmt = {"onsite": "Очно", "online": "Онлайн", "hybrid": "Смешанный"}[c.format]
            items.append((f"{c.title}\n{discipline.short_name} · {STATUS[c.state]}\n"
                          f"{c.start_date:%d.%m.%Y} — {c.end_date:%d.%m.%Y}, {start_time} ({c.timezone})\n{c.location} · {fmt}",
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
                rank = db.get(SportsRank, item["id"])
                if not allowed_athlete(db, actor, rank.athlete_id, rank.discipline_id):
                    continue
            path = f"/competitions/{item['id']}" if item["kind"].startswith("competition") else "/deadlines"
            items.append((f"{item['title']}\nСрок: {item['due_on']:%d.%m.%Y}", path))
    elif section == "assignments":
        if actor.role != "judge":
            return "Этот раздел доступен судьям.", menu(link.role)
        for item in assignments(actor=actor, db=db):
            items.append((f"{item['title']}\n{item['position']} · {item['start_date']:%d.%m.%Y}",
                          f"/competitions/{item['competition_id']}"))
    page = min(max(0, page), max(0, (len(items) - 1) // 5))
    chunk = items[page * 5:page * 5 + 5]
    text = f"{section_label(actor.role, section)} · {ROLE_NAMES[link.role]}\n\n"
    keyboard = []
    for i, (body, path) in enumerate(chunk, 1):
        text += f"{i}. {body[:600]}\n\n"
        label = body.split("\n", 1)[0][:55]
        keyboard.append([button(label, path=path)])
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
