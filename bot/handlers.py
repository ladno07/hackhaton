"""Telegram updates: identity comes only from the private chat, never callback IDs."""
from sqlalchemy import select
from app.models import TelegramLink, User
from app.services.telegram_link import claim, disconnect, normalize_code
from bot.schedule import roles_for
from bot.views import menu, render, button, url, ROLE_NAMES
from bot.telegram import TelegramError
from bot.navigation import reply_screen


def handle(db, api, update):
    callback = update.get("callback_query")
    message = (callback or {}).get("message") or update.get("message") or {}
    chat = message.get("chat", {})
    sender = (callback or message).get("from", {})
    if chat.get("type") != "private" or chat.get("id") != sender.get("id"):
        return
    chat_id = chat["id"]

    def reply(text, keyboard=None):
        return reply_screen(api, chat_id, text, keyboard,
                            previous_message_id=message.get("message_id") if callback else None)

    if callback:
        try:
            api.call("answerCallbackQuery", callback_query_id=callback["id"])
        except TelegramError as exc:
            if exc.code != 400:  # An old callback can expire while the bot is offline.
                raise
    text = message.get("text", "") if not callback else ""
    data = (callback or {}).get("data", "")
    if text.startswith("/") and text.split(maxsplit=1)[0].split("@", 1)[0] != "/start":
        reply("Доступна команда /start. Для выхода используйте кнопку «Выход из аккаунта» в меню.")
        return
    code_input = text
    if (code_input and code_input[0].isdigit()) or data.startswith("confirm:"):
        token = normalize_code(code_input) if text else data.removeprefix("confirm:")
        try:
            obj = claim(db, token, chat_id, confirm=bool(data))
            db.commit()
        except ValueError as exc:
            db.commit()  # Persist failed-attempt limits as well as successful code claims.
            reply(str(exc))
            return
        if text:
            reply(f"Подключить аккаунт «{obj.full_name}»? Если это не ваш аккаунт, не подтверждайте.",
                     [[button("Подтвердить подключение", f"confirm:{token}")]])
        else:
            reply("Telegram подключён. Здесь будут новые уведомления платформы.", menu(obj.role))
        return
    link = db.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id, TelegramLink.active.is_(True)).with_for_update())
    if not link:
        reply("Для подключения откройте сайт → Уведомления → Привязать Telegram.\n"
                 "Скопируйте одноразовый 8-значный код и отправьте его сюда сообщением. Код действует 10 минут.")
        return
    if data == "view:logout:0":
        from app.security import Actor
        from app.services.common import audit
        audit(db, Actor(db.get(User, link.user_id), link.role), "Отключение Telegram", link)
        disconnect(db, link)
        db.commit()
        reply("Вы вышли из аккаунта. Доставка уведомлений в Telegram отключена.\n"
              "Для повторного входа получите новый код на сайте и отправьте его боту.")
        return
    user = db.get(User, link.user_id)
    roles = roles_for(db, user.id)
    if data.startswith("site:"):
        path = data.removeprefix("site:")
        import re
        if not re.fullmatch(r"/(?:competitions/[0-9]+|notifications|ranks|deadlines)", path):
            reply("Эта ссылка недоступна. Откройте меню командой /start.")
            return
        reply(f"Адрес страницы: {url(path)}\n\n"
                 "Сайт запущен локально. Откройте этот адрес на компьютере с проектом. "
                 "Для доступа с телефона настройте доступный адрес в PUBLIC_SITE_URL.")
        return
    if data.startswith("role:"):
        role = data.removeprefix("role:")
        if role not in roles:
            reply("Этот кабинет недоступен.")
            return
        link.role = role
        db.commit()
        reply(f"Выбран кабинет: {ROLE_NAMES[role]}", menu(role))
        return
    section, page = "menu", 0
    if data.startswith("view:"):
        parts = data.split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            reply("Кнопка устарела. Откройте меню командой /start.")
            return
        section, page = parts[1], min(int(parts[2]), 100000)
    body, keyboard = render(db, link, user, section, page)
    db.commit()
    reply(body, keyboard)
