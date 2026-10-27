"""Minimal Telegram Bot API adapter; never log HTTP URLs containing the token."""
import httpx
from app.config import settings


class TelegramError(Exception):
    def __init__(self, code, retry_after=None, method=None, reason=None):
        self.code = code
        self.retry_after = retry_after
        self.method = method
        self.reason = reason
        super().__init__(f"Telegram API error {code}")


class Telegram:
    def __init__(self):
        self.client = httpx.Client(timeout=40)

    def call(self, method, **payload):
        try:
            response = self.client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}", json=payload
            )
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise TelegramError(0, method=method) from None
        if not data.get("ok"):
            description = str(data.get("description", "")).lower()
            reason = "button_url" if "url" in description else "callback_expired" if "query is too old" in description else "request_rejected"
            raise TelegramError(data.get("error_code", response.status_code),
                                data.get("parameters", {}).get("retry_after"), method=method, reason=reason)
        return data["result"]

    def send(self, chat_id, text, keyboard=None):
        keyboard = keyboard or []
        try:
            return self.call("sendMessage", chat_id=chat_id, text=text[:4000],
                             reply_markup={"inline_keyboard": keyboard})
        except TelegramError as exc:
            links = [b for row in keyboard for b in row if "url" in b]
            if exc.code != 400 or not links:
                raise
            # A rejected site URL must never make the whole menu silent.
            safe_keyboard = [[b for b in row if "url" not in b] for row in keyboard]
            suffix = "\n\n" + "\n".join(f"{b['text']}: {b['url']}" for b in links)
            return self.call("sendMessage", chat_id=chat_id, text=(text[:2500] + suffix)[:4000],
                             reply_markup={"inline_keyboard": [row for row in safe_keyboard if row]})

    def close(self):
        self.client.close()
