"""Effective finder settings = .env defaults, overridden by values saved in the
DB settings table (edited at runtime in the UI). Secrets (YouTube key, Telegram)
may be entered in the app on first run and are stored locally in data/finder.db.
"""
from __future__ import annotations

from typing import Optional

from .. import config
from . import db
from .models import SettingsUpdate

# setting key -> (.env default)
_DEFAULTS = {
    "youtube_api_key": config.YOUTUBE_API_KEY,
    "telegram_bot_token": config.TELEGRAM_BOT_TOKEN,
    "telegram_chat_id": config.TELEGRAM_CHAT_ID,
    "view_floor": config.FINDER_VIEW_FLOOR,
    "per_keyword": config.FINDER_PER_KEYWORD,
    "period_days": config.FINDER_PERIOD_DAYS,
    "regions": config.FINDER_REGIONS,
    "scan_hours": config.FINDER_SCAN_HOURS,
    "morning_hour": config.FINDER_MORNING_HOUR,
    "morning_enabled": False,
    "quota_limit": config.FINDER_QUOTA_LIMIT,
    "japan_check_top_n": config.FINDER_JAPAN_CHECK_TOP_N,
}

_SECRET_KEYS = {"youtube_api_key", "telegram_bot_token", "telegram_chat_id"}


def get(key: str):
    return db.get_setting(key, _DEFAULTS.get(key))


def current(*, redact_secrets: bool = True) -> dict:
    out = {}
    for key, default in _DEFAULTS.items():
        val = db.get_setting(key, default)
        if redact_secrets and key in _SECRET_KEYS:
            out[key] = bool(val)          # only expose whether it's set
            out[key + "_set"] = bool(val)
        else:
            out[key] = val
    return out


def update(patch: SettingsUpdate) -> dict:
    for key, val in patch.model_dump(exclude_none=True).items():
        db.set_setting(key, val)
    return current()


def youtube_key() -> str:
    return (get("youtube_api_key") or "").strip()


def telegram() -> tuple[str, str]:
    return (get("telegram_bot_token") or "").strip(), (get("telegram_chat_id") or "").strip()


def regions() -> list:
    r = get("regions") or config.FINDER_REGIONS
    return [str(x).upper() for x in r if str(x).strip()]


def quota_limit() -> int:
    try:
        return int(get("quota_limit"))
    except (TypeError, ValueError):
        return config.FINDER_QUOTA_LIMIT
