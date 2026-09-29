"""FastAPI routes for the 소재 찾기 tab, mounted at /api/finder."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import Response

from .. import config
from . import (channels, db, export, query, quota, report, scheduler, search,
               settings, telegram, youtube)
from .models import (CategoryCreate, KeywordCreate, RegisterChannelRequest,
                     SearchRequest, SettingsUpdate, ValidateKeysRequest, VideoPatch)

router = APIRouter(prefix="/api/finder", tags=["finder"])


@router.get("/health")
def health():
    db.init_db()
    return {
        "youtube_key": bool(settings.youtube_key()),
        "anthropic_key": bool(config.ANTHROPIC_API_KEY),
        "telegram": telegram.configured(),
    }


# --------------------------------------------------------------------------- #
# Settings + key validation
# --------------------------------------------------------------------------- #
@router.get("/settings")
def get_settings():
    db.init_db()
    return settings.current()


@router.put("/settings")
def put_settings(patch: SettingsUpdate):
    db.init_db()
    result = settings.update(patch)
    # 스캔 주기·아침 수집 시각/사용여부 변경을 재시작 없이 반영
    if any(v is not None for v in (patch.scan_hours, patch.morning_hour, patch.morning_enabled)):
        scheduler.reschedule()
    return result


@router.post("/validate_keys")
def validate_keys(req: ValidateKeysRequest):
    db.init_db()
    out = {}
    yt_key = (req.youtube_api_key if req.youtube_api_key is not None
              else settings.youtube_key())
    if yt_key:
        out["youtube"] = youtube.validate_key(yt_key)
    else:
        out["youtube"] = {"ok": False, "error": "키가 없습니다."}
    if req.telegram_bot_token:
        out["telegram"] = telegram.validate(req.telegram_bot_token,
                                            req.telegram_chat_id or "")
    return out


# --------------------------------------------------------------------------- #
# Quota + estimate
# --------------------------------------------------------------------------- #
@router.get("/quota")
def get_quota():
    db.init_db()
    return quota.status()


@router.post("/estimate")
def estimate(req: SearchRequest):
    db.init_db()
    pairs = search.resolve_keywords(req)
    regions = req.regions or settings.regions()
    per_kw = min(100, max(1, req.per_keyword or settings.get("per_keyword")))
    est = quota.estimate_search(len(pairs), len(regions), per_kw)
    est["keyword_count"] = len(pairs)
    est["region_count"] = len(regions)
    return est


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
@router.post("/search")
def start_search(req: SearchRequest, background: BackgroundTasks):
    db.init_db()
    if not settings.youtube_key():
        raise HTTPException(400, "YOUTUBE_API_KEY가 설정되지 않았습니다. 설정에서 키를 입력하세요.")
    pairs = search.resolve_keywords(req)
    if not pairs:
        raise HTTPException(400, "검색할 키워드가 없습니다.")
    run_id = search.new_run()
    background.add_task(search.run_search, req, run_id)
    return {"run_id": run_id}


@router.get("/search/{run_id}")
def search_status(run_id: str):
    run = search.get_run(run_id)
    if not run:
        raise HTTPException(404, "해당 검색 작업을 찾을 수 없습니다.")
    return run


# --------------------------------------------------------------------------- #
# Videos
# --------------------------------------------------------------------------- #
@router.get("/videos")
def list_videos(
    sort: str = "views",
    min_multiple: float = 0.0,
    min_views: int = 0,
    unentered_only: bool = False,
    small_channel_only: bool = False,
    hide_watched: bool = False,
    include_excluded: bool = False,
    category: str = "",
    region: str = "",
    status: str = "",
    limit: int = 500,
    offset: int = 0,
):
    db.init_db()
    rows = query.list_videos(
        sort=sort, min_multiple=min_multiple, min_views=min_views,
        unentered_only=unentered_only, small_channel_only=small_channel_only,
        hide_watched=hide_watched, include_excluded=include_excluded,
        category=category or None, region=region or None, status=status or None,
        limit=limit, offset=offset)
    return {"videos": rows, "counts": query.counts()}


@router.get("/videos/export.csv")
def export_csv(
    sort: str = "views", min_multiple: float = 0.0, min_views: int = 0,
    unentered_only: bool = False, small_channel_only: bool = False,
    hide_watched: bool = False, include_excluded: bool = False,
    category: str = "", region: str = "", status: str = "",
):
    db.init_db()
    rows = query.list_videos(
        sort=sort, min_multiple=min_multiple, min_views=min_views,
        unentered_only=unentered_only, small_channel_only=small_channel_only,
        hide_watched=hide_watched, include_excluded=include_excluded,
        category=category or None, region=region or None, status=status or None,
        limit=2000)
    csv_text = export.to_csv(rows)
    return Response(content=csv_text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=finder_videos.csv"})


@router.patch("/videos/{video_id}")
def patch_video(video_id: str, patch: VideoPatch):
    db.init_db()
    row = query.patch_video(video_id, status=patch.status, watched=patch.watched,
                            category=patch.category)
    if not row:
        raise HTTPException(404, "영상을 찾을 수 없습니다.")
    return row


# --------------------------------------------------------------------------- #
# Categories + keywords
# --------------------------------------------------------------------------- #
@router.get("/categories")
def list_categories():
    db.init_db()
    with db.get_conn() as c:
        rows = c.execute("SELECT * FROM categories ORDER BY id").fetchall()
    return db.rows_to_dicts(rows)


@router.post("/categories")
def add_category(req: CategoryCreate):
    db.init_db()
    with db.get_conn() as c:
        c.execute("INSERT OR IGNORE INTO categories(name, warn_tag) VALUES(?,?)",
                  (req.name, req.warn_tag))
    return list_categories()


@router.get("/keywords")
def list_keywords(category: str = ""):
    db.init_db()
    with db.get_conn() as c:
        if category:
            rows = c.execute("SELECT * FROM keywords WHERE category=? ORDER BY id",
                             (category,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM keywords ORDER BY category, id").fetchall()
    return db.rows_to_dicts(rows)


@router.post("/keywords")
def add_keyword(req: KeywordCreate):
    db.init_db()
    with db.get_conn() as c:
        c.execute("INSERT OR IGNORE INTO keywords(category, text, enabled) VALUES(?,?,1)",
                  (req.category, req.text.strip()))
    return list_keywords(req.category)


@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: int):
    db.init_db()
    with db.get_conn() as c:
        c.execute("DELETE FROM keywords WHERE id=?", (keyword_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Reference channels
# --------------------------------------------------------------------------- #
@router.get("/channels")
def list_channels():
    db.init_db()
    return {"channels": channels.list_reference()}


@router.post("/channels/{channel_id}/register")
def register_channel(channel_id: str, req: RegisterChannelRequest):
    db.init_db()
    if not settings.youtube_key():
        raise HTTPException(400, "YOUTUBE_API_KEY가 필요합니다.")
    try:
        return channels.register_reference(channel_id, req.category or "")
    except youtube.YouTubeError as e:
        raise HTTPException(400, str(e))


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str):
    db.init_db()
    channels.delete_reference(channel_id)
    return {"ok": True}


@router.post("/channels/scan")
def scan_channels(background: BackgroundTasks, channel_id: str = Query("")):
    db.init_db()
    if not settings.youtube_key():
        raise HTTPException(400, "YOUTUBE_API_KEY가 필요합니다.")
    background.add_task(channels.scan_reference, channel_id or None)
    return {"ok": True, "message": "레퍼런스 채널 스캔을 시작했습니다."}


# --------------------------------------------------------------------------- #
# Report + scheduler
# --------------------------------------------------------------------------- #
@router.get("/report/today")
def report_today():
    db.init_db()
    return report.today()


@router.get("/scheduler")
def scheduler_status():
    return scheduler.status()
