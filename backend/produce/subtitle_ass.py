"""세그먼트 → 스타일 있는 .ass 자막 생성 (libass 번인용).

가릴 띠(band) 안에 일본어 자막이 오도록 MarginV를 계산한다. 하단 중앙 정렬.
"""
from __future__ import annotations

from typing import List

from ..models import Segment


def _ass_time(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _clean_text(text: str) -> str:
    text = (text or "").replace("\r", "")
    # 모델이 넣은 줄바꿈 표기(\n 또는 실제 개행)를 ASS 개행(\N)으로
    text = text.replace("\\n", "\n").replace("\n", "\\N")
    text = text.replace("{", "(").replace("}", ")")  # ASS 오버라이드 블록 방지
    return text.strip()


def build_ass(segments: List[Segment], width: int, height: int,
              band_top: float, band_bottom: float, font_name: str = "Yu Gothic UI",
              font_scale: float = 1.0) -> str:
    width = max(1, int(width or 1080))
    height = max(1, int(height or 1920))
    font_size = max(18, int(height * 0.045 * (font_scale or 1.0)))
    outline = max(2, int(font_size * 0.09))
    # 자막을 가릴 띠 안쪽에 두기: 하단에서 (1 - band_bottom) 높이 + 약간의 여백
    margin_v = max(10, int(height * (1.0 - min(0.99, band_bottom)) + height * 0.012))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: JP,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,"
        f"1,0,0,0,100,100,0,0,1,{outline},1,2,60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = []
    for s in segments:
        txt = _clean_text(s.text_ja)
        if not txt or s.end <= s.start:
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(s.start)},{_ass_time(s.end)},JP,,0,0,0,,{txt}"
        )
    return header + "\n".join(lines) + "\n"
