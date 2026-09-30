"""Read-side: list collected videos with in-result sorting / filtering.

All filters operate on already-collected rows (no API calls), matching the spec's
"가져온 결과 안에서 즉시 적용" behavior.
"""
from __future__ import annotations

from typing import List, Optional

from . import db

SORT_COLUMNS = {
    "views": "views",
    "sub_multiple": "sub_multiple",
    "chan_avg_multiple": "chan_avg_multiple",
    "like_rate": "like_rate",
    "daily_views": "daily_views",
    "recent": "published_at",
}


def list_videos(*, sort: str = "views", min_multiple: float = 0.0,
                min_views: int = 0, unentered_only: bool = False,
                small_channel_only: bool = False, hide_watched: bool = False,
                include_excluded: bool = False, category: Optional[str] = None,
                region: Optional[str] = None, status: Optional[str] = None,
                limit: int = 500, offset: int = 0) -> List[dict]:
    where = []
    params: list = []
    if min_views > 0:
        where.append("views >= ?")
        params.append(min_views)
    if min_multiple > 0:
        # 배수 필터는 두 배수 중 큰 값 기준 (구독자대비 또는 채널평균대비 하나라도 충족)
        where.append("MAX(sub_multiple, chan_avg_multiple) >= ?")
        params.append(min_multiple)
    if unentered_only:
        where.append("japan_unentered = 1")
    if small_channel_only:
        where.append("subscribers < 100000")
    if hide_watched:
        where.append("watched = 0")
    if category:
        where.append("category = ?")
        params.append(category)
    if region:
        where.append("region = ?")
        params.append(region)
    if status:
        where.append("status = ?")
        params.append(status)
    elif not include_excluded:
        where.append("status != 'excluded'")

    order_col = SORT_COLUMNS.get(sort, "views")
    sql = "SELECT * FROM videos"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_col} DESC LIMIT ? OFFSET ?"
    params.extend([max(1, min(2000, limit)), max(0, offset)])
    with db.get_conn() as c:
        rows = c.execute(sql, params).fetchall()
    return db.rows_to_dicts(rows)


def get_video(video_id: str) -> Optional[dict]:
    with db.get_conn() as c:
        row = c.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
    return dict(row) if row else None


def patch_video(video_id: str, *, status: Optional[str] = None,
                watched: Optional[bool] = None, category: Optional[str] = None) -> Optional[dict]:
    sets, params = [], []
    if status is not None:
        sets.append("status=?")
        params.append(status)
    if watched is not None:
        sets.append("watched=?")
        params.append(1 if watched else 0)
    if category is not None:
        sets.append("category=?")
        sets.append("category_ai=0")     # 수동 변경 표시
        params.append(category)
    if not sets:
        return get_video(video_id)
    params.append(video_id)
    with db.get_conn() as c:
        c.execute(f"UPDATE videos SET {', '.join(sets)} WHERE video_id=?", params)
    return get_video(video_id)


def counts() -> dict:
    with db.get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM videos WHERE status!='excluded'").fetchone()[0]
        by_status = c.execute("SELECT status, COUNT(*) n FROM videos GROUP BY status").fetchall()
    return {"total": total, "by_status": {r["status"]: r["n"] for r in by_status}}
