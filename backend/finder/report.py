"""오늘의 리포트 — 수집된 영상/채널 데이터에서 6개 항목을 집계(추가 API 호출 없음)."""
from __future__ import annotations

import statistics
from typing import List

from . import db

SMALL_CHANNEL = 100_000     # 작은 채널 기준(구독자)
HOT_MULTIPLE = 5.0          # 요주의 판정 배수


def _median(values: List[int]) -> int:
    vals = [v for v in values if v]
    return int(statistics.median(vals)) if vals else 0


def today() -> dict:
    with db.get_conn() as c:
        # 1) 어제 대비 조회수 증가폭 큰 순
        gainers = c.execute(
            "SELECT video_id, title, title_ko, channel_title, views, prev_views, "
            "(views - prev_views) AS delta, region, category FROM videos "
            "WHERE prev_views IS NOT NULL AND views > prev_views AND status!='excluded' "
            "ORDER BY delta DESC LIMIT 20"
        ).fetchall()

        # 2) 오늘 새로 들어온 영상 수 + 카테고리별 분포
        new_today = c.execute(
            "SELECT COUNT(*) n FROM videos WHERE substr(first_seen,1,10)=date('now')"
        ).fetchone()["n"]
        new_by_cat = c.execute(
            "SELECT COALESCE(NULLIF(category,''),'(미분류)') cat, COUNT(*) n FROM videos "
            "WHERE substr(first_seen,1,10)=date('now') GROUP BY cat ORDER BY n DESC"
        ).fetchall()

        # 3) 요주의 채널: 구독 적은데 크게 터짐 (여러 편 / 한 편 구분)
        watch_rows = c.execute(
            "SELECT channel_id, channel_title, subscribers, "
            "COUNT(*) hits, MAX(sub_multiple) max_mult, MAX(views) max_views "
            "FROM videos WHERE subscribers>0 AND subscribers < ? AND sub_multiple >= ? "
            "AND status!='excluded' GROUP BY channel_id ORDER BY max_mult DESC LIMIT 30",
            (SMALL_CHANNEL, HOT_MULTIPLE),
        ).fetchall()

        # 4) 카테고리별 편수 + 조회수 (중앙값은 파이썬에서)
        cat_rows = c.execute(
            "SELECT COALESCE(NULLIF(category,''),'(미분류)') cat, views FROM videos "
            "WHERE status!='excluded'"
        ).fetchall()

        # 5) 일본 미진출 목록
        unentered = c.execute(
            "SELECT video_id, title, title_ko, channel_title, views, sub_multiple, region, category "
            "FROM videos WHERE japan_unentered=1 AND status!='excluded' "
            "ORDER BY views DESC LIMIT 40"
        ).fetchall()

        # 6) 영상 구조 통계 (수집 가능한 범위)
        dur_rows = c.execute(
            "SELECT duration_sec, has_caption FROM videos WHERE status!='excluded'"
        ).fetchall()

    # 카테고리별 중앙값 집계
    by_cat: dict = {}
    for r in cat_rows:
        by_cat.setdefault(r["cat"], []).append(r["views"])
    cat_stats = [
        {"category": cat, "count": len(v), "median_views": _median(v)}
        for cat, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1]))
    ]

    # 요주의 채널 분리
    multi = [dict(r) for r in watch_rows if r["hits"] >= 2]
    single = [dict(r) for r in watch_rows if r["hits"] == 1]

    # 길이 분포 버킷 + 자막 유무
    buckets = {"0-15s": 0, "16-30s": 0, "31-60s": 0, "61-120s": 0, "121-180s": 0}
    caption_yes = caption_no = caption_unknown = 0
    for r in dur_rows:
        d = r["duration_sec"] or 0
        if d <= 15: buckets["0-15s"] += 1
        elif d <= 30: buckets["16-30s"] += 1
        elif d <= 60: buckets["31-60s"] += 1
        elif d <= 120: buckets["61-120s"] += 1
        else: buckets["121-180s"] += 1
        if r["has_caption"] == 1: caption_yes += 1
        elif r["has_caption"] == 0: caption_no += 1
        else: caption_unknown += 1

    return {
        "gainers": db.rows_to_dicts(gainers),
        "new_today": {"count": new_today,
                      "by_category": [dict(r) for r in new_by_cat]},
        "watch_channels": {"multi": multi, "single": single},
        "category_stats": cat_stats,
        "unentered": db.rows_to_dicts(unentered),
        "structure": {"duration_buckets": buckets,
                      "caption": {"yes": caption_yes, "no": caption_no,
                                  "unknown": caption_unknown}},
    }


def summary_line(rep: dict) -> str:
    """텔레그램/로그용 한 줄 요약."""
    n = rep["new_today"]["count"]
    g = len(rep["gainers"])
    u = len(rep["unentered"])
    w = len(rep["watch_channels"]["multi"]) + len(rep["watch_channels"]["single"])
    return f"오늘 신규 {n}편 · 급등 {g}편 · 미진출 {u}편 · 요주의 채널 {w}곳"
