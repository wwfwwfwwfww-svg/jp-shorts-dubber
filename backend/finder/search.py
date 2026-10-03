"""Bulk search orchestration: keyword bundles × country distribution → filter
(<=180s, exclude ko/ja) → metrics (both multiples) → SQLite upsert.

A search run is tracked in an in-memory registry so the UI can poll progress; the
collected videos themselves are persisted to data/finder.db (survive restarts).
"""
from __future__ import annotations

import datetime as _dt
import math
import threading
import uuid
from typing import Callable, Dict, List, Optional, Tuple

from .. import config
from ..common import llm
from . import channels, db, filters, metrics, quota, settings, youtube
from .models import SearchRequest

_runs: Dict[str, dict] = {}
_runs_lock = threading.Lock()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Run registry
# --------------------------------------------------------------------------- #
def new_run() -> str:
    run_id = uuid.uuid4().hex[:12]
    with _runs_lock:
        _runs[run_id] = {"id": run_id, "status": "running", "message": "시작 중...",
                         "collected": 0, "new": 0, "quota_used": 0, "error": None}
    return run_id


def _update_run(run_id: str, **fields) -> None:
    with _runs_lock:
        if run_id in _runs:
            _runs[run_id].update(fields)


def get_run(run_id: str) -> Optional[dict]:
    with _runs_lock:
        r = _runs.get(run_id)
        return dict(r) if r else None


# --------------------------------------------------------------------------- #
# Keyword resolution
# --------------------------------------------------------------------------- #
def resolve_keywords(req: SearchRequest) -> List[Tuple[str, str]]:
    """Return list of (keyword, category). Manual keywords have category ''."""
    pairs: List[Tuple[str, str]] = [(k.strip(), "") for k in req.keywords if k.strip()]
    if req.categories:
        with db.get_conn() as c:
            for cat in req.categories:
                rows = c.execute(
                    "SELECT text FROM keywords WHERE category=? AND enabled=1", (cat,)
                ).fetchall()
                for r in rows:
                    pairs.append((r["text"], cat))
    # de-dup by keyword, keep first category seen
    seen = {}
    for kw, cat in pairs:
        if kw not in seen:
            seen[kw] = cat
    return [(kw, cat) for kw, cat in seen.items()]


# --------------------------------------------------------------------------- #
# Persist
# --------------------------------------------------------------------------- #
def persist_videos(details: List[dict], *, region: str = "",
                   region_map: Optional[Dict[str, str]] = None,
                   category_map: Optional[Dict[str, str]] = None,
                   category: str = "", view_floor: Optional[int] = None) -> int:
    """Filter + score + upsert videos.list items. Returns count of newly-added rows."""
    keep = [it for it in details
            if filters.duration_ok(it)
            and not filters.is_korean_or_japanese(it)
            and not filters.is_non_target(it)]   # 인도·동남아 등 비서구 재업로드 제외
    if not keep:
        return 0

    channel_ids = [it.get("snippet", {}).get("channelId", "") for it in keep]
    chan_rows = channels.ensure_channels(channel_ids)

    new_count = 0
    for it in keep:
        vid = it.get("id")
        snip = it.get("snippet", {})
        stats = it.get("statistics", {})
        cid = snip.get("channelId", "")
        chan = chan_rows.get(cid, {})
        # 비서구 재업로드 채널 제외(채널 국가 기준). 국가 미설정이면 통과(완벽 X).
        if (chan.get("country") or "").upper() in filters.BLOCK_CHANNEL_COUNTRIES:
            continue
        views = int(stats.get("viewCount", 0) or 0)
        if view_floor and views < view_floor:
            continue
        likes = int(stats.get("likeCount", 0) or 0)
        subs = int(chan.get("subscribers", 0) or 0)
        chan_avg = channels.avg_views(cid, chan.get("uploads_playlist", "")) if cid else 0.0
        m = metrics.compute(views, likes, subs, chan_avg, snip.get("publishedAt", ""))
        dur = filters.parse_duration(it.get("contentDetails", {}).get("duration", ""))
        thumb = (snip.get("thumbnails", {}).get("medium", {})
                 or snip.get("thumbnails", {}).get("default", {})).get("url", "")
        vid_region = (region_map or {}).get(vid, region)
        vid_category = (category_map or {}).get(vid, category)
        has_caption = 1 if (it.get("contentDetails", {}).get("caption") == "true") else 0

        if _upsert_video(
            video_id=vid, snippet=snip, views=views, likes=likes, subs=subs,
            duration=dur, metrics_=m, region=vid_region, category=vid_category,
            thumbnail=thumb, has_caption=has_caption,
        ):
            new_count += 1
    return new_count


def _upsert_video(*, video_id, snippet, views, likes, subs, duration, metrics_,
                  region, category, thumbnail, has_caption) -> bool:
    """Insert or update one video. On update, roll current views into prev_views.
    Returns True if the row was newly inserted."""
    now = _now()
    with db.get_conn() as c:
        existing = c.execute("SELECT views, prev_views, first_seen, status, category, "
                             "category_ai, watched FROM videos WHERE video_id=?",
                             (video_id,)).fetchone()
        if existing is None:
            c.execute(
                "INSERT INTO videos(video_id, title, channel_id, channel_title, "
                "published_at, duration_sec, views, likes, subscribers, sub_multiple, "
                "chan_avg_multiple, daily_views, like_rate, region, lang, category, "
                "thumbnail, has_caption, first_seen, collected_at, status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new')",
                (video_id, snippet.get("title", ""), snippet.get("channelId", ""),
                 snippet.get("channelTitle", ""), snippet.get("publishedAt", ""),
                 duration, views, likes, subs, metrics_["sub_multiple"],
                 metrics_["chan_avg_multiple"], metrics_["daily_views"],
                 metrics_["like_rate"], region, snippet.get("defaultAudioLanguage", ""),
                 category, thumbnail, has_caption, now, now),
            )
            return True
        # Update: preserve prior views for day-over-day comparison, keep user state.
        prev_views = existing["views"]
        keep_category = existing["category"] or category
        c.execute(
            "UPDATE videos SET title=?, views=?, likes=?, subscribers=?, sub_multiple=?, "
            "chan_avg_multiple=?, daily_views=?, like_rate=?, prev_views=?, prev_views_at=?, "
            "collected_at=?, region=COALESCE(NULLIF(?,''), region), category=? WHERE video_id=?",
            (snippet.get("title", ""), views, likes, subs, metrics_["sub_multiple"],
             metrics_["chan_avg_multiple"], metrics_["daily_views"], metrics_["like_rate"],
             prev_views, now, now, region, keep_category, video_id),
        )
        return False


# --------------------------------------------------------------------------- #
# Title translation (optional, cheap Claude model)
# --------------------------------------------------------------------------- #
def translate_titles(limit: int = 60) -> int:
    """Fill title_ko for videos missing it, in one batched cheap call. Best-effort."""
    if not config.ANTHROPIC_API_KEY:
        return 0
    with db.get_conn() as c:
        rows = c.execute("SELECT video_id, title FROM videos "
                         "WHERE (title_ko IS NULL OR title_ko='') AND title!='' "
                         "ORDER BY collected_at DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return 0
    items = [{"id": r["video_id"], "t": r["title"]} for r in rows]
    prompt = (
        "다음은 해외 쇼츠 영상 제목 목록입니다. 각 제목을 자연스러운 한국어로 번역하세요. "
        "고유명사는 무리하게 바꾸지 말고 의미가 통하게. 출력은 JSON 배열만: "
        '[{"id":"...","ko":"한국어 제목"}]. 설명 금지.\n\n'
        + _compact_json(items)
    )
    try:
        data = llm.complete_json(prompt, max_tokens=2000)
    except Exception:
        return 0
    if not isinstance(data, list):
        return 0
    n = 0
    with db.get_conn() as c:
        for d in data:
            if isinstance(d, dict) and d.get("id") and d.get("ko"):
                c.execute("UPDATE videos SET title_ko=? WHERE video_id=?",
                          (str(d["ko"]).strip(), d["id"]))
                n += 1
    return n


def _compact_json(items) -> str:
    import json
    return json.dumps(items, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #
def run_search(req: SearchRequest, run_id: str,
               progress: Optional[Callable[[str], None]] = None) -> None:
    def emit(msg):
        _update_run(run_id, message=msg)
        if progress:
            progress(msg)

    try:
        db.init_db()
        from .models import PERIOD_DAYS
        pairs = resolve_keywords(req)
        if not pairs:
            _update_run(run_id, status="error", error="검색할 키워드가 없습니다.")
            return
        regions = [r.upper() for r in (req.regions or settings.regions())] or ["US"]
        per_keyword = min(100, max(1, req.per_keyword or settings.get("per_keyword")))
        view_floor = req.view_floor if req.view_floor is not None else settings.get("view_floor")
        days = PERIOD_DAYS.get(req.period, 14)
        published_after = youtube.published_after_iso(days)
        pages = max(1, math.ceil(per_keyword / 50))
        order = "date" if req.order == "date" else "viewCount"

        limit = settings.quota_limit()
        seen_region: Dict[str, str] = {}
        seen_category: Dict[str, str] = {}
        order_ids: List[str] = []

        total_units = len(pairs) * len(regions)
        unit = 0
        for kw, cat in pairs:
            for region in regions:
                unit += 1
                if quota.used_today() + quota.SEARCH_COST > limit:
                    emit("쿼터 한도 근접 — 검색을 중단합니다.")
                    _update_run(run_id, status="stopped_quota")
                    break
                emit(f"검색 중 [{unit}/{total_units}] '{kw}' · {region}")
                token = None
                for _ in range(pages):
                    try:
                        res = youtube.search(
                            kw, region=region, order=order,
                            published_after=published_after,
                            max_results=50, page_token=token)
                    except youtube.YouTubeError as e:
                        emit(f"검색 오류({region}): {e}")
                        break
                    for it in res.get("items", []):
                        vid = (it.get("id") or {}).get("videoId")
                        if vid and vid not in seen_region:
                            seen_region[vid] = region
                            seen_category[vid] = cat
                            order_ids.append(vid)
                    token = res.get("nextPageToken")
                    if not token:
                        break
                _update_run(run_id, collected=len(order_ids), quota_used=quota.used_today())
            else:
                continue
            break  # propagate quota stop out of the keyword loop

        # Fetch details + persist in batches of 50.
        emit(f"상세 정보 조회 중... (후보 {len(order_ids)}개)")
        new_total = 0
        for i in range(0, len(order_ids), 50):
            chunk = order_ids[i:i + 50]
            try:
                details = youtube.videos_details(chunk)
            except youtube.YouTubeError as e:
                emit(f"상세 조회 오류: {e}")
                break
            new_total += persist_videos(
                details, region_map=seen_region, category_map=seen_category,
                view_floor=view_floor)
            _update_run(run_id, new=new_total, quota_used=quota.used_today())

        if req.translate_titles and config.ANTHROPIC_API_KEY:
            emit("제목 한국어 번역 중...")
            try:
                translate_titles()
            except Exception:
                pass

        _update_run(run_id, status="done",
                    message=f"완료 — 신규 {new_total}개 / 후보 {len(order_ids)}개",
                    new=new_total, collected=len(order_ids),
                    quota_used=quota.used_today())
    except Exception as e:  # pragma: no cover - surface unexpected failures
        _update_run(run_id, status="error", error=str(e), message=f"오류: {e}")
