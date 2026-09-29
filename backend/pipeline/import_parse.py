"""Parse a subtitle analysis pasted from a Claude chat into Segment objects.

Primary (recommended) format — one line per subtitle:
    start | end | 나레이션|대사 | 텍스트
e.g.
    0.0 | 2.0 | 나레이션 | 여자는 양초 기름을 손톱 틈새에 부은 뒤

Also tolerant of:
  - an optional leading index cell:  1 | 0.0 | 2.0 | 나레이션 | 텍스트
  - markdown tables (leading/trailing pipes, header/separator rows are skipped)
  - arrow format without pipes:      #1  0:00.0 → 0:02.0  나레이션  텍스트
  - times as seconds (4.5) or mm:ss(.s) (1:23.5)
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..models import Segment

# A timestamp is either MM:SS(.s) (minutes:seconds) or a plain seconds value.
# Plain seconds must allow 3+ digits (e.g. 101.0, 152.2) — videos run past 100s.
_TIME_RE = re.compile(r"^(?:\d{1,2}:\d{1,2}|\d+)(?:\.\d+)?$")
_TIME_TOKEN = r"(?:\d{1,2}:\d{1,2}|\d+)(?:\.\d+)?"
_ARROW_RE = re.compile(
    rf"({_TIME_TOKEN})\s*(?:→|->|~|—|–|-)\s*({_TIME_TOKEN})"
)

_NARR = ("나레이션", "나래이션", "narration", "흰색", "white")
_DIAL = ("대사", "dialogue", "유채색", "초록", "녹색", "green")


def _is_time(s: str) -> bool:
    return bool(_TIME_RE.match(s.strip()))


def _parse_time(s: str) -> float:
    s = s.strip()
    if ":" in s:
        mm, ss = s.split(":", 1)
        return round(int(mm) * 60 + float(ss), 3)
    return round(float(s), 3)


def _detect_type(s: str) -> Optional[str]:
    for k in _DIAL:
        if k in s:
            return "dialogue"
    for k in _NARR:
        if k in s:
            return "narration"
    return None


def _clean_text(text: str) -> str:
    text = text.strip().strip("|·—-–:\"'` ")
    return re.sub(r"\s+", " ", text).strip()


def _strip_type_tokens(text: str) -> str:
    """Remove a standalone type keyword (arrow format only, where the type word
    sits next to the text). Only whitespace-bounded matches, so a subtitle that
    genuinely contains e.g. '대사' is not damaged."""
    for k in _NARR + _DIAL:
        text = re.sub(rf"(?:^|\s){re.escape(k)}(?=\s|$)", " ", text)
    return text


def _mk(start: float, end: float, seg_type: str, text: str) -> Optional[Segment]:
    text = _clean_text(text)
    if not text:
        return None
    if end < start:
        start, end = end, start
    return Segment(
        index=0,
        start=start,
        end=end,
        duration=round(max(0.0, end - start), 3),
        text_kr=text,
        type=seg_type,
        color="white" if seg_type == "narration" else "green",
    )


def _parse_line(line: str) -> Optional[Segment]:
    line = line.strip()
    if not line:
        return None
    # skip markdown separators / pure punctuation rows
    if set(line) <= set("|-:= "):
        return None

    if "|" in line:
        cells = [c.strip() for c in line.split("|") if c.strip() != ""]
        if len(cells) < 3:
            return None
        text = cells[-1]
        pre = cells[:-1]
        type_idx = next((i for i, c in enumerate(pre) if _detect_type(c)), None)
        seg_type = _detect_type(pre[type_idx]) if type_idx is not None else "narration"
        nums = [c for i, c in enumerate(pre) if i != type_idx and _is_time(c)]
        if len(nums) < 2:
            return None
        return _mk(_parse_time(nums[-2]), _parse_time(nums[-1]), seg_type, text)

    # arrow / whitespace format
    line2 = re.sub(r"^\s*#?\d+[.\):]?\s+", "", line)  # strip leading index like "#1 " / "1) "
    m = _ARROW_RE.search(line2)
    if not m:
        return None
    start, end = _parse_time(m.group(1)), _parse_time(m.group(2))
    rest = (line2[: m.start()] + " " + line2[m.end():]).strip()
    seg_type = _detect_type(rest) or "narration"
    return _mk(start, end, seg_type, _strip_type_tokens(rest))


def parse_ja_lines(raw: str) -> List[tuple]:
    """Parse pasted Japanese translation lines into (start, end, text) tuples.

    Format: `start | end | 일본어텍스트` (optional leading index, arrow format and
    mm:ss times also accepted). Used to apply chat-translated Japanese onto the
    existing segments, matched by start time.
    """
    out: List[tuple] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or set(line) <= set("|-:= "):
            continue
        if "|" in line:
            cells = [c.strip() for c in line.split("|") if c.strip() != ""]
            if len(cells) < 3:
                continue
            text = cells[-1]
            nums = [c for c in cells[:-1] if _is_time(c)]
            if len(nums) < 2:
                continue
            start, end = _parse_time(nums[-2]), _parse_time(nums[-1])
        else:
            line2 = re.sub(r"^\s*#?\d+[.\):]?\s+", "", line)
            m = _ARROW_RE.search(line2)
            if not m:
                continue
            start, end = _parse_time(m.group(1)), _parse_time(m.group(2))
            text = (line2[: m.start()] + " " + line2[m.end():]).strip()
        text = _clean_text(text)
        if text:
            out.append((start, end, text))
    return out


def segments_from_ja(raw: str) -> List[Segment]:
    """Build segments directly from a pasted Japanese script (start | end | 일본어).
    text_ja is filled; text_kr is left empty. Used for the direct Japanese path."""
    segments: List[Segment] = []
    for i, (start, end, text) in enumerate(parse_ja_lines(raw), start=1):
        if end < start:
            start, end = end, start
        segments.append(Segment(
            index=i,
            start=start,
            end=end,
            duration=round(max(0.0, end - start), 3),
            text_kr="",
            text_ja=text,
            type="narration",
            color="white",
        ))
    return segments


def apply_ja_to_segments(segments: List[Segment], raw: str) -> int:
    """Apply parsed Japanese lines onto segments, matched by nearest start time.
    Returns how many segments received Japanese text."""
    lines = parse_ja_lines(raw)
    if not lines:
        return 0
    matched = 0
    # If counts line up, trust order; otherwise match each line to nearest start.
    if len(lines) == len(segments):
        for seg, (_s, _e, text) in zip(segments, lines):
            seg.text_ja = text
            matched += 1
        return matched
    for (start, _end, text) in lines:
        seg = min(segments, key=lambda s: abs(s.start - start))
        seg.text_ja = text
        matched += 1
    return matched


def parse_pasted_segments(raw: str) -> List[Segment]:
    segments: List[Segment] = []
    for line in raw.splitlines():
        seg = _parse_line(line)
        if seg is not None:
            segments.append(seg)
    for i, seg in enumerate(segments, start=1):
        seg.index = i
    return segments
