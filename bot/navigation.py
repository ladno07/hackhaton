"""Replace a clicked navigation screen only after the new one has been sent."""
import logging
from bot.telegram import TelegramError

log = logging.getLogger("fsp.bot")


def reply_screen(api, chat_id, text, keyboard=None, previous_message_id=None):
    result = api.send(chat_id, text, keyboard)
    new_id = result.get("message_id") if isinstance(result, dict) else None
    if previous_message_id and previous_message_id != new_id:
        try:
            api.call("deleteMessage", chat_id=chat_id, message_id=previous_message_id)
        except TelegramError as exc:
            # A missing/old screen must not undo the new successful response.
            log.info("Previous navigation message could not be removed: code %s", exc.code)
    return result
