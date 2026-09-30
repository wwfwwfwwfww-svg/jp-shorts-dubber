"""Per-video performance metrics.

- 구독자 대비 배수 = views / subscribers  (영상 자체가 터진 정도; >=10이면 UI 빨간글씨)
- 채널평균 대비 배수 = views / (채널 최근 쇼츠 평균 조회수)
- 하루 평균 조회수 = views / 업로드 후 경과 일수(최소 1)
- 좋아요율 = likes / views
"""
from __future__ import annotations

import datetime as _dt

SUB_MULTIPLE_HOT = 10.0   # 이 이상이면 강조


def days_since(published_at: str) -> float:
    if not published_at:
        return 1.0
    try:
        ts = _dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    delta = _dt.datetime.now(_dt.timezone.utc) - ts
    return max(1.0, delta.total_seconds() / 86400.0)


def compute(views: int, likes: int, subscribers: int, chan_avg: float,
            published_at: str) -> dict:
    views = max(0, int(views or 0))
    likes = max(0, int(likes or 0))
    subscribers = max(0, int(subscribers or 0))
    sub_multiple = round(views / subscribers, 2) if subscribers > 0 else 0.0
    chan_avg_multiple = round(views / chan_avg, 2) if chan_avg and chan_avg > 0 else 0.0
    daily = round(views / days_since(published_at), 1)
    like_rate = round(likes / views, 4) if views > 0 else 0.0
    return {
        "sub_multiple": sub_multiple,
        "chan_avg_multiple": chan_avg_multiple,
        "daily_views": daily,
        "like_rate": like_rate,
    }
