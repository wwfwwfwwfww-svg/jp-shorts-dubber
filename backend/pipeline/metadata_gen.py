"""Stage 4: title / thumbnail / description / tags from the final Japanese script.
All fields in Japanese + Korean pairs. Text-only Claude call.
"""
from __future__ import annotations

from typing import List

from .. import config
from ..models import Segment
from .translate import _client, _extract_json, msg_text


def generate_metadata(segments: List[Segment], model: str = "", title: str = "") -> dict:
    script_ja = "\n".join(s.text_ja for s in segments if s.text_ja)
    title_note = (f"참고: 이 작품의 제목은 '{title}' 입니다. "
                  "단, 태그(tags)에는 영화/드라마 제목을 절대 넣지 마세요.\n\n") if title else \
                 "태그(tags)에는 영화/드라마 제목을 넣지 마세요.\n\n"
    prompt = (
        "다음은 완성된 일본 영화요약 쇼츠의 일본어 나레이션 전문입니다. 조회수·시청지속을 극대화하는"
        " 메타데이터를 만드세요. 모든 항목은 일본어(ja)와 한국어(ko)를 함께 제공합니다.\n\n"
        + title_note +
        "썸네일 문구 규칙: 스크롤을 멈추게 하는 강력한 '후킹' 문구를 서로 다른 각도로 5개 만드세요"
        "(궁금증·반전 암시·감정 자극 등). 각 후보는 2줄, 한 줄당 8~10자 이내로 간결하게(일본어는"
        " 공간을 더 차지하므로 짧게). 결말/핵심 반전은 스포하지 말고 초반 훅만.\n"
        "태그 규칙: 검색·노출에 도움되는 태그 10개 내외. 영화/드라마 제목은 제외.\n\n"
        "출력은 JSON 객체만:\n"
        "{\n"
        '  "titles": [{"ja":"40자 이내·후킹 앞배치","ko":"..."}, {"ja":"...","ko":"..."}, {"ja":"...","ko":"..."}],\n'
        '  "thumbnails": [{"ja_lines":["1줄","2줄"], "ko_lines":["1줄","2줄"]}, ...총 5개],\n'
        '  "description": {"ja":"설명 + #shorts 포함 해시태그 3~5", "ko":"..."},\n'
        '  "tags": ["태그1", "...총 10개 내외, 제목 제외"]\n'
        "}\n\n"
        f"나레이션 전문:\n{script_ja}"
    )
    client = _client()
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=4000,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(msg_text(msg))
