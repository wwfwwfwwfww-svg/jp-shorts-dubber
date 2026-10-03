"""Channel stats, recent-average-views cache (24h), and reference channels.

The reference-channel scan (quota saver) collects a registered channel's newest
uploads for 1-2 points instead of a 100-point search. It is wired to the
scheduler in Milestone B but the register/list/delete/scan primitives live here.
"""
from __future__ import annotations

import datetime as _dt
import statistics
from typing import Dict, List, Optional

from . import db, youtube

AVG_CACHE_HOURS = 24
RECENT_SHORTS = 20


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _fresh(iso_ts: Optional[str], hours: int) -> bool:
    if not iso_ts:
        return False
    try:
        ts = _dt.datetime.fromisoformat(iso_ts)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return (_dt.datetime.now(_dt.timezone.utc) - ts) < _dt.timedelta(hours=hours)


def upsert_channel(item: dict) -> dict:
    cid = item.get("id")
    snip = item.get("snippet", {})
    stats = item.get("statistics", {})
    uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
    subs = int(stats.get("subscriberCount", 0) or 0)
    country = (snip.get("country", "") or "").upper()
    with db.get_conn() as c:
        c.execute(
            "INSERT INTO channels(channel_id, title, subscribers, uploads_playlist, country, added_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET "
            "title=excluded.title, subscribers=excluded.subscribers, "
            "country=COALESCE(NULLIF(excluded.country,''), channels.country), "
            "uploads_playlist=COALESCE(NULLIF(excluded.uploads_playlist,''), channels.uploads_playlist)",
            (cid, snip.get("title", ""), subs, uploads, country, _now()),
        )
    return {"channel_id": cid, "title": snip.get("title", ""),
            "subscribers": subs, "uploads_playlist": uploads, "country": country}


def ensure_channels(channel_ids: List[str]) -> Dict[str, dict]:
    """Return {channel_id: row-dict}, fetching+caching any not already stored."""
    ids = list(dict.fromkeys(cid for cid in channel_ids if cid))
    if not ids:
        return {}
    with db.get_conn() as c:
        rows = c.execute(
            f"SELECT * FROM channels WHERE channel_id IN ({','.join('?' * len(ids))})", ids
        ).fetchall()
    have = {r["channel_id"]: dict(r) for r in rows}
    missing = [cid for cid in ids if cid not in have]
    if missing:
        fetched = youtube.channels_details(missing)
        for cid, item in fetched.items():
            upsert_channel(item)
        # re-read
        with db.get_conn() as c:
            rows = c.execute(
                f"SELECT * FROM channels WHERE channel_id IN ({','.join('?' * len(ids))})", ids
            ).fetchall()
        have = {r["channel_id"]: dict(r) for r in rows}
    return have


def avg_views(channel_id: str, uploads_playlist: str = "") -> float:
    """Recent-shorts average views for a channel, cached 24h. 2 quota points on miss."""
    with db.get_conn() as c:
        row = c.execute("SELECT avg_views, avg_cached_at, uploads_playlist "
                        "FROM channels WHERE channel_id=?", (channel_id,)).fetchone()
    if row and _fresh(row["avg_cached_at"], AVG_CACHE_HOURS) and row["avg_views"]:
        return float(row["avg_views"])
    playlist = uploads_playlist or (row["uploads_playlist"] if row else "")
    if not playlist:
        return 0.0
    try:
        vids = youtube.playlist_video_ids(playlist, limit=RECENT_SHORTS)
        details = youtube.videos_details(vids) if vids else []
    except youtube.YouTubeError:
        return float(row["avg_views"]) if row and row["avg_views"] else 0.0
    view_counts = [int(v.get("statistics", {}).get("viewCount", 0) or 0) for v in details]
    view_counts = [v for v in view_counts if v > 0]
    avg = float(round(statistics.mean(view_counts))) if view_counts else 0.0
    with db.get_conn() as c:
        c.execute("UPDATE channels SET avg_views=?, avg_cached_at=? WHERE channel_id=?",
                  (avg, _now(), channel_id))
    return avg


# --------------------------------------------------------------------------- #
# Reference channels
# --------------------------------------------------------------------------- #
def register_reference(channel_id: str, category: str = "") -> dict:
    ensure_channels([channel_id])
    with db.get_conn() as c:
        c.execute("UPDATE channels SET is_reference=1, ref_category=? WHERE channel_id=?",
                  (category or "", channel_id))
        row = c.execute("SELECT * FROM channels WHERE channel_id=?", (channel_id,)).fetchone()
    return dict(row) if row else {"channel_id": channel_id}


def delete_reference(channel_id: str) -> None:
    with db.get_conn() as c:
        c.execute("UPDATE channels SET is_reference=0 WHERE channel_id=?", (channel_id,))


def list_reference() -> List[dict]:
    with db.get_conn() as c:
        rows = c.execute(
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM videos v WHERE v.channel_id=c.channel_id) AS recent_hits "
            "FROM channels c WHERE is_reference=1 ORDER BY added_at DESC"
        ).fetchall()
    return db.rows_to_dicts(rows)


def scan_reference(channel_id: Optional[str] = None) -> dict:
    """Collect newest uploads from reference channels (cheap: 1-2 pts/channel)."""
    from . import search  # lazy import to avoid a cycle
    with db.get_conn() as c:
        if channel_id:
            rows = c.execute("SELECT * FROM channels WHERE channel_id=? AND is_reference=1",
                             (channel_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM channels WHERE is_reference=1").fetchall()
    total_new = 0
    scanned = 0
    for r in rows:
        playlist = r["uploads_playlist"]
        if not playlist:
            info = youtube.channels_details([r["channel_id"]]).get(r["channel_id"])
            if info:
                upsert_channel(info)
                playlist = info.get("contentDetails", {}).get(
                    "relatedPlaylists", {}).get("uploads", "")
        if not playlist:
            continue
        try:
            vids = youtube.playlist_video_ids(playlist, limit=RECENT_SHORTS)
            details = youtube.videos_details(vids) if vids else []
        except youtube.YouTubeError:
            continue
        added = search.persist_videos(details, region="레퍼런스",
                                      category=r["ref_category"] or "")
        total_new += added
        scanned += 1
        with db.get_conn() as c:
            c.execute("UPDATE channels SET last_scan_at=? WHERE channel_id=?",
                      (_now(), r["channel_id"]))
    return {"channels_scanned": scanned, "new_videos": total_new}
