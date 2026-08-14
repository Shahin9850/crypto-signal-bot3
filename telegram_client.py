"""
Minimal synchronous Telegram Bot API client using `requests`. No async, no
long-lived connection -- built for a script that runs once, does its work,
and exits (perfect for a GitHub Actions cron job every 15 minutes).
"""
import requests


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"

    def send_message(self, chat_id, text: str):
        resp = requests.post(
            f"{self.base}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_updates(self, offset: int = None, timeout: int = 0):
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        resp = requests.get(f"{self.base}/getUpdates", params=params, timeout=timeout + 15)
        resp.raise_for_status()
        return resp.json().get("result", [])
