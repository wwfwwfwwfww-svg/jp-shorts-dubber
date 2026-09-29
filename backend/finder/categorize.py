"""AI category classification from title + thumbnail (cheap Claude model, batched).

Sends a batch of videos (thumbnail image + title) in one multimodal call and
asks Claude to bucket each into one of the user's categories. Result is stored
with category_ai=1 so the UI can show "AI 추정" and let the user override.
"""
from __future__ import annotations

from typing import List, Optional

import httpx

from ..common import llm
from . import db

BATCH = 8


def _category_names() -> List[str]:
    with db.get_conn() as c:
        rows = c.execute("SELECT name FROM categories ORDER BY id").fetchall()
    return [r["name"] for r in rows]


def _fetch_thumb(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(url)
        return r.content if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def _classify_batch(rows: List[dict], categories: List[str]) -> int:
    images = []
    listing = []
    for i, v in enumerate(rows):
        raw = _fetch_thumb(v.get("thumbnail", ""))
        if raw:
            images.append(llm.image_block_from_bytes(raw, "image/jpeg"))
        else:
            images.append(llm.image_block_from_bytes(b"", "image/jpeg"))  # placeholder keeps order
        listing.append(f'{i}: "{v.get("title", "")}"')
    prompt = (
        "다음은 해외 쇼츠 영상들입니다. 각 영상의 썸네일 이미지(순서대로 첨부)와 제목을 보고 "
        "가장 알맞은 카테고리 하나로 분류하세요.\n"
        f"허용 카테고리: {', '.join(categories)}\n"
        "판단이 어려우면 가장 근접한 것으로. 출력은 JSON 배열만: "
        '[{"index":0,"category":"동물"}]. 설명 금지.\n\n제목:\n' + "\n".join(listing)
    )
    try:
        data = llm.complete_json(prompt, images=images, max_tokens=1500)
    except Exception:
        return 0
    if not isinstance(data, list):
        return 0
    valid = set(categories)
    n = 0
    with db.get_conn() as c:
        for d in data:
            if not isinstance(d, dict):
                continue
            idx = d.get("index")
            cat = str(d.get("category", "")).strip()
            if isinstance(idx, int) and 0 <= idx < len(rows) and cat in valid:
                c.execute("UPDATE videos SET category=?, category_ai=1 WHERE video_id=?",
                          (cat, rows[idx]["video_id"]))
                n += 1
    return n


def categorize(video_ids: Optional[List[str]] = None, limit: int = 40) -> dict:
    db.init_db()
    categories = _category_names()
    if not categories:
        return {"classified": 0, "error": "카테고리가 없습니다."}
    with db.get_conn() as c:
        if video_ids:
            ph = ",".join("?" * len(video_ids))
            rows = c.execute(f"SELECT video_id, title, thumbnail FROM videos "
                             f"WHERE video_id IN ({ph})", video_ids).fetchall()
        else:
            rows = c.execute("SELECT video_id, title, thumbnail FROM videos "
                             "WHERE (category IS NULL OR category='') AND status!='excluded' "
                             "ORDER BY views DESC LIMIT ?", (limit,)).fetchall()
    rows = [dict(r) for r in rows]
    total = 0
    for i in range(0, len(rows), BATCH):
        total += _classify_batch(rows[i:i + BATCH], categories)
    return {"classified": total, "considered": len(rows)}
