"""Optional Telegram notifications. No-op (returns False) when unconfigured, so
the rest of the finder works fine without a bot token.
"""
from __future__ import annotations

import httpx

from . import settings


def configured() -> bool:
    token, chat = settings.telegram()
    return bool(token and chat)


def send(text: str) -> bool:
    token, chat = settings.telegram()
    if not (token and chat):
        return False
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
            )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def validate(token: str, chat_id: str) -> dict:
    """Check a bot token (getMe) and, if chat_id given, that we can reach it."""
    if not token:
        return {"ok": False, "error": "봇 토큰이 없습니다."}
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"https://api.telegram.org/bot{token}/getMe")
        if r.status_code != 200 or not r.json().get("ok"):
            return {"ok": False, "error": "봇 토큰이 유효하지 않습니다."}
        return {"ok": True, "bot": r.json().get("result", {}).get("username", "")}
    except httpx.HTTPError as e:
        return {"ok": False, "error": str(e)}
