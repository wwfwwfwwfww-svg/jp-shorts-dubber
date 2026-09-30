"""Stage 2: reconstruct the source script into Japanese narration (Claude).

Not a per-line translation: Claude reads the whole story and rewrites it in
Japanese at the story level (merging/splitting/omitting allowed) so the TOTAL
Japanese length lands in a character budget that yields ONE uniform speaking
speed (TARGET_SPEED_MIN..MAX). A Python character count drives a feedback loop —
the model's own count is never trusted.
"""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

from .. import config
from ..common import llm
from ..models import Job, Segment

# Characters that do NOT count toward the budget (whitespace + punctuation).
_PUNCT = set("、。，．！？!?…「」『』（）()【】《》・:：;；~〜「」\"'`.,·—–-‥　 \t\n\r")


def count_chars(text: str) -> int:
    return sum(1 for ch in (text or "") if ch not in _PUNCT and not ch.isspace())


# The Anthropic client + JSON helpers now live in ``common.llm`` (shared with the
# 소재 찾기 tab). These thin aliases keep the original names/behaviour so every
# existing import (``from .translate import msg_text`` etc.) still works unchanged.
def _client():
    return llm.client()


msg_text = llm.msg_text
_extract_json = llm.extract_json


def _system_prompt() -> str:
    return (
        "당신은 일본 영화요약 쇼츠의 프로 나레이션 각본가입니다. 아래 원본 나레이션(언어 무관 — "
        "한국어·영어·중국어 등 무엇이든)"
        " 구간 전체를 먼저 다 읽고 스토리 흐름을 파악한 뒤, 스토리/줄거리 레벨에서 자연스러운 일본어"
        " 나레이션으로 재구성하세요.\n\n"
        "규칙:\n"
        "1) 문장 단위 직역 금지. 문장을 합치거나 생략해도 되지만 스토리(줄거리)를 훼손하지 마세요.\n"
        "2) 자연스러운 나레이션 문어체(〜だった / 〜していた 등).\n"
        "3) 세그먼트 하나당 최대 " + str(config.MAX_CHARS_PER_SEGMENT) + "자(13자×2줄). 넘으면 쉼표로 잇지 말고"
        " 별도의 타이밍 구간으로 분리하세요.\n"
        "4) 각 세그먼트에 대해 자연스러운 한국어 역번역(text_ja_back)도 같이 쓰세요. 원문 그대로가 아니라"
        " '지금 일본어가 실제로 하는 말'을 옮긴 것입니다.\n"
        "5) start/end(초)는 원본 구간 범위 안에서 순서대로 배정하세요(겹치지 않게).\n"
        "6) 목표: 일본어 전체 글자수가 지정된 범위에 '들어오도록' 분량을 충분히 채우세요. 목표보다"
        " 짧으면 안 됩니다. 짧으면 장면 묘사·인물의 감정·행동 디테일을 더 넣고, 한 문장을 두 구간으로"
        " 나눠 구간 수를 늘려서라도 목표 글자수에 최대한 근접시키세요(스토리 훼손은 금지).\n"
        "7) 출력은 JSON 배열만: [{\"start\":number,\"end\":number,\"type\":\"narration|dialogue\","
        "\"text_ja\":\"...\",\"text_ja_back\":\"...\"}]. 설명 금지."
    )


def _user_prompt(segments: List[Segment], cmin: int, cmax: int, feedback: str) -> str:
    src = [
        {"index": s.index, "start": s.start, "end": s.end,
         "type": s.type, "text": s.text_kr}
        for s in segments
    ]
    parts = [
        f"목표 일본어 총 글자수 범위: {cmin} ~ {cmax}자 (공백·문장부호 제외 기준).",
        "원본 구간:",
        json.dumps(src, ensure_ascii=False, indent=1),
    ]
    if feedback:
        parts.insert(0, feedback)
    return "\n".join(parts)


def _generate(segments, cmin, cmax, feedback, model) -> List[dict]:
    client = _client()
    msg = client.messages.create(
        model=model or config.ANTHROPIC_MODEL,
        max_tokens=16000,
        thinking={"type": "disabled"},
        system=_system_prompt(),
        messages=[{"role": "user", "content": _user_prompt(segments, cmin, cmax, feedback)}],
    )
    data = _extract_json(msg_text(msg))
    return data if isinstance(data, list) else []


def active_seconds(segments: List[Segment]) -> float:
    """Narration active span = last subtitle end − first subtitle start.

    NOT the sum of per-segment durations (that discards the silent gaps between
    subtitles and makes the budget — and the final dub — far too short on videos
    with narration pauses). The span matches the source video length closely, so
    the sequential dub lands near the original length.
    """
    starts = [s.start for s in segments if s.text_kr or s.text_ja]
    ends = [s.end for s in segments if s.text_kr or s.text_ja]
    if not starts or not ends:
        return round(sum(max(0.0, s.duration) for s in segments), 3)
    return round(max(0.0, max(ends) - min(starts)), 3)


def translate_story(job: Job, on_progress=None, model: Optional[str] = None) -> None:
    """Reconstruct job.segments into Japanese in place, set job.speed and budget."""
    def progress(m):
        if on_progress:
            on_progress(m)

    active = active_seconds(job.segments) or 1.0
    cps = config.NATURAL_CHARS_PER_SEC
    cmin = int(round(active * cps * config.TARGET_SPEED_MIN))
    cmax = int(round(active * cps * config.TARGET_SPEED_MAX))
    job.active_seconds = active
    job.char_target_min, job.char_target_max = cmin, cmax

    source = list(job.segments)
    # Accept a small tolerance around the tight target to avoid extra full
    # regenerations (each costs a whole-script generation).
    accept_lo = int(cmin * 0.95)
    accept_hi = int(cmax * 1.05)
    best: Tuple[int, List[dict]] = (10 ** 9, [])
    feedback = ""
    max_attempts = 4

    for attempt in range(max_attempts):
        progress(f"일본어 재구성 중... (시도 {attempt + 1}/{max_attempts})")
        data = _generate(source, cmin, cmax, feedback, model)
        if not data:
            continue
        total = sum(count_chars(d.get("text_ja", "")) for d in data)
        dist = 0 if accept_lo <= total <= accept_hi else min(abs(total - cmin), abs(total - cmax))
        if dist < best[0]:
            best = (dist, data)
        if accept_lo <= total <= accept_hi:
            break
        if total > cmax:
            feedback = f"직전 결과는 총 {total}자로 깁니다. 약 {total - cmax + 10}자 줄여 다시 작성하세요."
        else:
            need = cmin - total + 20
            feedback = (f"직전 결과는 총 {total}자로 목표({cmin}~{cmax})보다 {cmin - total}자 부족합니다. "
                        f"장면 묘사·감정·디테일을 더해 약 {need}자 늘리고, 구간 수도 늘려서 반드시 {cmin}자 이상으로 다시 작성하세요.")

    data = best[1]

    # Rebuild segments from the reconstructed list.
    segs: List[Segment] = []
    for i, d in enumerate(data, start=1):
        try:
            start = round(float(d.get("start", 0.0)), 3)
            end = round(float(d.get("end", start)), 3)
        except (TypeError, ValueError):
            start, end = 0.0, 0.0
        if end < start:
            start, end = end, start
        typ = "dialogue" if str(d.get("type", "")).lower().startswith("dial") else "narration"
        segs.append(Segment(
            index=i, start=start, end=end, duration=round(max(0.0, end - start), 3),
            text_kr="", type=typ, color="white" if typ == "narration" else "green",
            text_ja=(d.get("text_ja") or "").strip(),
            text_ja_back=(d.get("text_ja_back") or "").strip(),
        ))
    if segs:
        job.segments = segs

    job.char_actual = sum(count_chars(s.text_ja) for s in job.segments)
    # Single speed to fit the target span, clamped to the target range so the
    # narration never slows below 1.10 (a short script just ends a bit early
    # rather than dragging). No per-segment speeds.
    raw_speed = job.char_actual / (active * cps) if active else 1.0
    job.speed = round(min(config.TARGET_SPEED_MAX,
                          max(config.SPEED_FLOOR, raw_speed)), 3)
