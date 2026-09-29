"""YouTube Data API quota accounting (points/day).

Cost model (v3): search.list = 100 points; videos/channels/playlistItems.list =
1 point per call (each call can carry up to 50 ids). The daily cap is ~10,000,
so search is the expensive part — the UI shows an estimate before every run and
warns as the day's usage approaches the limit.
"""
from __future__ import annotations

import datetime as _dt
import math

from . import db, settings

SEARCH_COST = 100
LIST_COST = 1
PAGE_SIZE = 50


def _today() -> str:
    return _dt.date.today().isoformat()


def add_points(n: int) -> None:
    if n <= 0:
        return
    with db.get_conn() as c:
        c.execute(
            "INSERT INTO quota_log(date, points_used) VALUES(?, ?) "
            "ON CONFLICT(date) DO UPDATE SET points_used = points_used + ?",
            (_today(), n, n),
        )


def used_today() -> int:
    with db.get_conn() as c:
        row = c.execute("SELECT points_used FROM quota_log WHERE date=?", (_today(),)).fetchone()
    return int(row["points_used"]) if row else 0


def status() -> dict:
    limit = settings.quota_limit()
    used = used_today()
    return {
        "date": _today(),
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "near_limit": used >= limit * 0.9,
    }


def estimate_search(keyword_count: int, region_count: int, per_keyword: int) -> dict:
    """Estimate points for a bulk search. search.list dominates."""
    region_count = max(1, region_count)
    keyword_count = max(0, keyword_count)
    pages = max(1, math.ceil(min(per_keyword, 100) / PAGE_SIZE))
    search_calls = keyword_count * region_count * pages
    search_points = search_calls * SEARCH_COST

    # Detail lookups (videos.list) + channel stats (channels.list), batched by 50.
    approx_videos = keyword_count * region_count * per_keyword
    detail_calls = math.ceil(approx_videos / PAGE_SIZE) if approx_videos else 0
    # channels.list ~ one batch per 50 unique channels (assume ~70% unique).
    channel_calls = math.ceil(approx_videos * 0.7 / PAGE_SIZE) if approx_videos else 0
    detail_points = (detail_calls + channel_calls) * LIST_COST

    total = search_points + detail_points
    st = status()
    return {
        "search_calls": search_calls,
        "search_points": search_points,
        "detail_points": detail_points,
        "estimated_points": total,
        "used_today": st["used"],
        "limit": st["limit"],
        "would_exceed": st["used"] + total > st["limit"],
    }
