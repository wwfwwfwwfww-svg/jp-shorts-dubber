"""자막 충실형 일본어 번역 — 화면 번인 영어 자막을 그 뜻 그대로 일본어 자막으로.

기존 translate.py(스토리 재구성)와 다르다: 여기서는 **줄 단위로 의미를 유지**하고
타이밍도 원본 구간을 그대로 쓴다. Claude 텍스트 1회 배치 호출(저비용).
"""
from __future__ import annotations

import json
from typing import List

from ..common import llm
from ..models import Segment

MAX_CHARS_PER_LINE = 13     # 2줄 × 약 13자 권장(쇼츠 가독성)


def _prompt(segments: List[Segment]) -> str:
    items = [{"i": s.index, "text": (s.text_kr or s.text_ko or "")} for s in segments if (s.text_kr or s.text_ko)]
    return (
        "다음은 해외 쇼츠 영상의 '화면에 박힌 자막'을 순서대로 읽은 것입니다(주로 영어). "
        "각 자막을 **자연스러운 일본어 자막**으로 옮기세요. 규칙:\n"
        "1) 뜻을 유지하되 쇼츠 자막답게 짧고 간결하게. 한 구간은 최대 2줄, 한 줄 약 13자 이내. "
        "줄바꿈이 필요하면 text_ja 안에 \\n 을 넣으세요.\n"
        "2) 고유명사·숫자는 유지. 영상에 없는 내용 추가 금지.\n"
        "3) 각 구간의 한국어 역번역(text_ja_back)도 함께.\n"
        "4) 출력은 JSON 배열만: [{\"i\":번호,\"text_ja\":\"일본어\",\"text_ja_back\":\"한국어\"}]. 설명 금지.\n\n"
        + json.dumps(items, ensure_ascii=False)
    )


def translate(segments: List[Segment]) -> List[Segment]:
    """Fill text_ja / text_ja_back on each segment in place. Returns the list."""
    targets = [s for s in segments if (s.text_kr or s.text_ko)]
    if not targets:
        return segments
    data = llm.complete_json(_prompt(segments), max_tokens=4000)
    if not isinstance(data, list):
        return segments
    by_index = {s.index: s for s in segments}
    for d in data:
        if not isinstance(d, dict):
            continue
        seg = by_index.get(d.get("i"))
        if seg is not None:
            seg.text_ja = str(d.get("text_ja", "")).strip()
            seg.text_ja_back = str(d.get("text_ja_back", "")).strip()
    return segments
