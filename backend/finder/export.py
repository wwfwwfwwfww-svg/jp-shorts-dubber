"""CSV export of the currently-filtered video list."""
from __future__ import annotations

import csv
import io
from typing import List

_COLUMNS = [
    ("video_id", "video_id"),
    ("title", "제목"),
    ("title_ko", "제목(한국어)"),
    ("channel_title", "채널"),
    ("subscribers", "구독자"),
    ("views", "조회수"),
    ("sub_multiple", "구독자대비배수"),
    ("chan_avg_multiple", "채널평균대비배수"),
    ("daily_views", "하루평균조회수"),
    ("like_rate", "좋아요율"),
    ("published_at", "업로드일"),
    ("duration_sec", "길이(초)"),
    ("region", "국가"),
    ("category", "카테고리"),
    ("japan_unentered", "일본미진출"),
    ("status", "상태"),
]


def to_csv(rows: List[dict]) -> str:
    buf = io.StringIO()
    buf.write("﻿")   # BOM so Excel reads UTF-8 (Korean) correctly
    writer = csv.writer(buf)
    writer.writerow([label for _, label in _COLUMNS])
    for r in rows:
        writer.writerow([r.get(key, "") for key, _ in _COLUMNS])
    return buf.getvalue()
