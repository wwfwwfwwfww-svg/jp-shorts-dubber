"""YouTube Data API v3 HTTP client (direct calls, precise quota accounting).

Every call records its point cost via ``quota`` so the UI can show usage. Uses
httpx synchronously (called from FastAPI background/threadpool tasks).
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

import httpx

from . import quota, settings

BASE = "https://www.googleapis.com/youtube/v3"

# regionCode -> relevanceLanguage (spread search beyond the anglosphere).
REGION_LANG = {
    "US": "en", "GB": "en", "CA": "en", "AU": "en", "IE": "en", "NZ": "en",
    "DE": "de", "AT": "de", "FR": "fr", "ES": "es", "MX": "es", "AR": "es",
    "BR": "pt", "PT": "pt", "ID": "id", "IN": "hi", "IT": "it", "NL": "nl",
    "TR": "tr", "PL": "pl", "RU": "ru", "VN": "vi", "TH": "th",
    "JP": "ja",   # 일본 미진출 판별 시 일본 내 유사 영상 검색용
}


class YouTubeError(RuntimeError):
    pass


def region_language(region: str) -> str:
    return REGION_LANG.get((region or "").upper(), "en")


def _key(explicit: Optional[str]) -> str:
    key = (explicit or settings.youtube_key()).strip()
    if not key:
        raise YouTubeError("YOUTUBE_API_KEY가 설정되지 않았습니다. 설정에서 키를 입력하세요.")
    return key


def _get(endpoint: str, params: dict, cost: int, key: Optional[str] = None) -> dict:
    params = dict(params)
    params["key"] = _key(key)
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(f"{BASE}/{endpoint}", params=params)
    except httpx.HTTPError as e:
        raise YouTubeError(f"네트워크 오류: {e}") from e
    # Record quota even on failure for over-quota/403 (the request still counted
    # server-side in most cases); harmless slight over-count for a local tool.
    quota.add_points(cost)
    if r.status_code == 200:
        return r.json()
    detail = ""
    try:
        detail = r.json().get("error", {}).get("message", "")
    except Exception:
        detail = r.text[:200]
    if r.status_code == 403 and "quota" in detail.lower():
        raise YouTubeError(f"YouTube API 쿼터를 초과했습니다: {detail}")
    if r.status_code in (400, 403):
        raise YouTubeError(f"YouTube API 오류({r.status_code}): {detail}")
    raise YouTubeError(f"YouTube API 오류({r.status_code}): {detail}")


def validate_key(key: str) -> dict:
    """Cheap 1-point call to confirm the key works."""
    try:
        _get("i18nLanguages", {"part": "snippet", "hl": "en"}, cost=1, key=key)
        return {"ok": True}
    except YouTubeError as e:
        return {"ok": False, "error": str(e)}


def search(query: str, *, region: str, order: str = "viewCount",
           published_after: Optional[str] = None, max_results: int = 50,
           page_token: Optional[str] = None, key: Optional[str] = None) -> dict:
    """search.list (100 points). Returns {'items':[...ids+snippet], 'nextPageToken':...}."""
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "order": order,
        "maxResults": min(50, max(1, max_results)),
        "videoDuration": "short",         # <4min prefilter; re-filtered to <=180s later
        "regionCode": (region or "US").upper(),
        "relevanceLanguage": region_language(region),
    }
    if published_after:
        params["publishedAfter"] = published_after
    if page_token:
        params["pageToken"] = page_token
    return _get("search", params, cost=quota.SEARCH_COST, key=key)


def videos_details(video_ids: List[str], key: Optional[str] = None) -> List[dict]:
    """videos.list (snippet+statistics+contentDetails), 1 point per 50 ids."""
    out: List[dict] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        data = _get("videos", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "maxResults": 50,
        }, cost=quota.LIST_COST, key=key)
        out.extend(data.get("items", []))
    return out


def channels_details(channel_ids: List[str], key: Optional[str] = None) -> dict:
    """channels.list (snippet+statistics+contentDetails). Returns {channel_id: item}."""
    result: dict = {}
    uniq = list(dict.fromkeys(cid for cid in channel_ids if cid))
    for i in range(0, len(uniq), 50):
        chunk = uniq[i:i + 50]
        data = _get("channels", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "maxResults": 50,
        }, cost=quota.LIST_COST, key=key)
        for item in data.get("items", []):
            result[item["id"]] = item
    return result


def playlist_video_ids(playlist_id: str, limit: int = 20, key: Optional[str] = None) -> List[str]:
    """Most recent video ids from an uploads playlist (playlistItems.list, 1pt/page)."""
    if not playlist_id:
        return []
    data = _get("playlistItems", {
        "part": "contentDetails",
        "playlistId": playlist_id,
        "maxResults": min(50, max(1, limit)),
    }, cost=quota.LIST_COST, key=key)
    ids = []
    for item in data.get("items", []):
        vid = item.get("contentDetails", {}).get("videoId")
        if vid:
            ids.append(vid)
    return ids[:limit]


def published_after_iso(days: Optional[int]) -> Optional[str]:
    if not days:
        return None
    dt = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
