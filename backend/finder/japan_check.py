"""「일본 미진출」 판별 — 선점 소재 찾기.

영상의 핵심 키워드를 AI가 일본어로 뽑아, 일본(regionCode=JP, relevanceLanguage=ja)
에서 유사한 일본어 쇼츠가 있는지 검색한다. 유사 영상이 없으면 미진출(초록 배지).

쿼터를 많이 쓰므로(영상당 search.list 1회 = 100p) **버튼/상위 N개 한정**으로만 실행
하고, 결과는 japan_check 테이블에 캐시해 재실행하지 않는다. 자동 전체 실행 금지.
"""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from ..common import llm
from . import db, settings, youtube


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _select_targets(video_ids: Optional[List[str]], top_n: int) -> List[dict]:
    with db.get_conn() as c:
        if video_ids:
            ph = ",".join("?" * len(video_ids))
            rows = c.execute(
                f"SELECT video_id, title, description FROM videos WHERE video_id IN ({ph})",
                video_ids).fetchall()
        else:
            # 배수 상위 N개 중 아직 판별 안 된 것
            rows = c.execute(
                "SELECT v.video_id, v.title, v.description FROM videos v "
                "LEFT JOIN japan_check j ON j.video_id=v.video_id "
                "WHERE j.video_id IS NULL AND v.status!='excluded' "
                "ORDER BY MAX(v.sub_multiple, v.chan_avg_multiple) DESC LIMIT ?",
                (top_n,)).fetchall()
    return [dict(r) for r in rows]


def _jp_queries(rows: List[dict]) -> dict:
    """Batch: title -> a short Japanese search query. {video_id: jp_query}."""
    listing = [f'{i}: "{r["title"]}"' for i, r in enumerate(rows)]
    prompt = (
        "다음 해외 쇼츠 제목들에서 각 영상의 핵심 소재를 뽑아 '일본어 검색어' 한 개로 만드세요"
        "(일본에서 유사 영상을 찾기 위한 짧은 일본어 키워드). 출력은 JSON 배열만: "
        '[{"index":0,"jp":"日本語キーワード"}]. 설명 금지.\n\n' + "\n".join(listing))
    out = {}
    try:
        data = llm.complete_json(prompt, max_tokens=1200)
        if isinstance(data, list):
            for d in data:
                if isinstance(d, dict) and isinstance(d.get("index"), int):
                    idx = d["index"]
                    if 0 <= idx < len(rows):
                        out[rows[idx]["video_id"]] = str(d.get("jp", "")).strip()
    except Exception:
        pass
    return out


def run(video_ids: Optional[List[str]] = None, top_n: Optional[int] = None) -> dict:
    db.init_db()
    n = top_n or settings.get("japan_check_top_n") or 20
    rows = _select_targets(video_ids, int(n))
    if not rows:
        return {"checked": 0, "unentered": 0}
    queries = _jp_queries(rows)
    checked = unentered = 0
    for r in rows:
        vid = r["video_id"]
        jp = queries.get(vid) or r["title"]
        try:
            res = youtube.search(jp, region="JP", order="relevance", max_results=5)
        except youtube.YouTubeError:
            continue
        found = len(res.get("items", []))
        is_unentered = 1 if found == 0 else 0
        checked += 1
        unentered += is_unentered
        with db.get_conn() as c:
            c.execute(
                "INSERT INTO japan_check(video_id, unentered, jp_keywords, checked_at) "
                "VALUES(?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET "
                "unentered=excluded.unentered, jp_keywords=excluded.jp_keywords, "
                "checked_at=excluded.checked_at",
                (vid, is_unentered, jp, _now()))
            c.execute("UPDATE videos SET japan_unentered=? WHERE video_id=?",
                      (is_unentered, vid))
    return {"checked": checked, "unentered": unentered}
