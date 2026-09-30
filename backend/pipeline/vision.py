"""Stage 1: read burned-in subtitles with Claude Vision (no OCR).

Sampled subtitle-band frames are assembled into timestamp-labeled contact sheets
(grids). Each sheet is sent to a vision-capable Claude model, which reads the text
directly and returns timed subtitle segments. Works for any on-screen language
(Korean, English, mixed).
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import List, Tuple

import cv2
from PIL import Image, ImageDraw, ImageFont

from .. import config
from ..common import llm
from ..models import Segment
from . import frames as frames_util

LABEL_H = 34

SYSTEM_PROMPT = (
    "당신은 영상 자막을 읽는 전문가입니다. 입력 이미지는 세로 영화요약 쇼츠의 '하단 자막 영역'"
    " 프레임들을 격자로 붙인 콘택트시트이고, 각 셀 좌상단에 그 프레임의 시각(초)이 노란 라벨로 적혀"
    " 있습니다. 프레임 간격은 0.5초입니다.\n\n"
    "규칙:\n"
    "1) OCR처럼 기계적으로가 아니라 이미지를 직접 보고 자막 텍스트를 정확히 읽으세요(오타 없이).\n"
    "2) 같은 자막이 여러 프레임 연속으로 보이면 하나의 구간으로 묶고, 자막이 바뀌는 정확한 시각을"
    " 라벨 기준으로 start/end로 특정하세요. end는 그 자막이 마지막으로 보인 프레임의 다음 프레임 시각.\n"
    "3) 자막 글자색이 흰색이면 type=\"narration\", 다른 색(초록 등 영화 대사)이면 type=\"dialogue\".\n"
    "4) 자막이 없는 빈 프레임은 건너뜁니다.\n"
    "5) text 필드에는 화면에 보이는 언어 그대로 읽으세요(원문 유지). 언어 무관 — 한국어·영어·"
    "일본어·중국어·스페인어·태국어 등 어떤 언어든. lang 필드에 ISO 코드(ko/en/ja/zh/es/th…)를 표기.\n"
    "6) text_ko 필드에는 그 자막을 자연스러운 한국어로 옮겨 적으세요(사용자가 내용을 이해하기 위함)."
    " 원문이 한국어면 text와 동일하게.\n"
    "7) 출력은 JSON 배열만. 각 요소: {\"start\":초(number),\"end\":초(number),\"text\":\"원문\","
    "\"text_ko\":\"한국어번역\",\"type\":\"narration|dialogue\",\"lang\":\"es\"}. 설명 문장 금지."
)


def _font():
    for path in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(path, 26)
        except Exception:
            continue
    return ImageFont.load_default()


_FONT = None


def _cell(crop_bgr, ts_label: str, cell_w: int) -> Image.Image:
    global _FONT
    if _FONT is None:
        _FONT = _font()
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    ratio = cell_w / pil.width
    cell_h = max(1, int(pil.height * ratio))
    pil = pil.resize((cell_w, cell_h))
    canvas = Image.new("RGB", (cell_w, cell_h + LABEL_H), (18, 18, 18))
    canvas.paste(pil, (0, LABEL_H))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, cell_w, LABEL_H], fill=(0, 0, 0))
    d.text((6, 3), ts_label, fill=(255, 235, 0), font=_FONT)
    return canvas


def build_contact_sheets(frame_paths, top, bottom, interval, out_dir) -> List[Tuple[Path, float, float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    cols, rows = config.CONTACT_COLS, config.CONTACT_ROWS
    per = cols * rows
    cell_w = config.CONTACT_CELL_W
    indexed = list(enumerate(frame_paths))
    sheets: List[Tuple[Path, float, float]] = []

    for s_i in range(0, len(indexed), per):
        group = indexed[s_i:s_i + per]
        cells = []
        for gidx, fp in group:
            img = cv2.imread(str(fp))
            if img is None:
                continue
            crop = frames_util.crop_band(img, top, bottom)
            ts = frames_util.frame_time(gidx, interval)
            cells.append((_cell(crop, f"{ts:.1f}s", cell_w), ts))
        if not cells:
            continue
        cw = cell_w
        ch = max(c.height for c, _ in cells)
        sheet = Image.new("RGB", (cols * cw, rows * ch), (10, 10, 10))
        for i, (c, _) in enumerate(cells):
            r, cc = divmod(i, cols)
            sheet.paste(c, (cc * cw, r * ch))
        p = out_dir / f"sheet_{s_i // per:03d}.png"
        sheet.save(p)
        sheets.append((p, cells[0][1], cells[-1][1]))
    return sheets


def _client():
    return llm.client()


def _detect_crop(client, frame_paths, out_dir) -> tuple:
    """Auto-locate the subtitle's vertical band by showing Claude a few FULL frames.
    Returns (top_ratio, bottom_ratio) with padding, or (None, None) if unknown."""
    from .translate import msg_text
    n = len(frame_paths)
    if n == 0:
        return None, None
    idxs = sorted(set(int(i * (n - 1) / 8) for i in range(9)))
    cells = []
    for gi in idxs:
        img = cv2.imread(str(frame_paths[gi]))
        if img is None:
            continue
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        w = 300
        pil = pil.resize((w, int(pil.height * w / pil.width)))
        cells.append(pil)
    if not cells:
        return None, None
    cols = 3
    cw, ch = cells[0].width, cells[0].height
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (10, 10, 10))
    for i, c in enumerate(cells):
        r, cc = divmod(i, cols)
        sheet.paste(c, (cc * cw, r * ch))
    p = out_dir / "_detect.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(p)
    b64 = base64.b64encode(p.read_bytes()).decode()
    prompt = (
        "각 셀은 세로 쇼츠 영상의 '전체 프레임'입니다. 화면에 박힌(번인) 자막 텍스트가 세로로"
        " 어디에 있는지 보고, 자막 텍스트 영역을 감싸는 위쪽/아래쪽 위치를 0(맨위)~1(맨아래)"
        " 비율로 추정하세요. 여러 줄이면 전체를 감싸는 범위. 자막이 안 보이면 top=0,bottom=1."
        " JSON 객체 하나만: {\"top\":0.x,\"bottom\":0.y}. 설명 금지."
    )
    try:
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL, max_tokens=300, thinking={"type": "disabled"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt}]}],
        )
        m = re.search(r"\{[^}]*\}", msg_text(msg))
        d = json.loads(m.group(0)) if m else {}
        top = float(d.get("top", 0.0)); bottom = float(d.get("bottom", 1.0))
    except Exception:
        return None, None
    if bottom - top < 0.03 or (top <= 0.02 and bottom >= 0.98):
        return None, None  # unreliable / whole frame
    return max(0.0, top - 0.08), min(1.0, bottom + 0.08)


def _extract_json_array(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return []
    return []


def _read_sheet(client, sheet_path: Path, t0: float, t1: float) -> list:
    b64 = base64.b64encode(sheet_path.read_bytes()).decode()
    from .translate import msg_text
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=6000,
        thinking={"type": "disabled"},
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": (
                    f"이 콘택트시트의 시간 범위는 약 {t0:.1f}s ~ {t1:.1f}s 입니다. "
                    "규칙에 따라 자막 구간을 JSON 배열로만 반환하세요."
                )},
            ],
        }],
    )
    return _extract_json_array(msg_text(msg))


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or ""))


def summarize_story(segments: List[Segment]) -> dict:
    """One cheap text call: turn the raw extracted lines into a coherent Korean plot
    summary and guess the movie/drama title. Returns {summary_ko, title_ja, title_ko}."""
    from .translate import _extract_json, msg_text
    lines = [(s.text_ko or s.text_kr or "").strip() for s in segments]
    joined = " ".join(t for t in lines if t)
    if not joined:
        return {"summary_ko": "", "title_ja": "", "title_ko": ""}
    prompt = (
        "아래는 어떤 영화(또는 드라마) 요약 쇼츠에서 화면 자막을 순서대로 읽어 뽑은 것입니다. 낱말·어순이"
        " 깨져 있을 수 있습니다. 이걸 바탕으로 다음을 하세요.\n"
        "1) 전체 줄거리를 처음부터 끝까지 자연스러운 한국어 문단으로 매끄럽게 정리(사건 순서·인물 관계"
        " 유지, 결말까지 포함). 읽어서 내용을 바로 이해할 수 있게.\n"
        "2) 어떤 영화/드라마인지 제목을 추정(일본어 제목 title_ja, 한국어 제목 title_ko). 확실하지 않으면"
        " 가장 그럴듯한 후보 하나. 도저히 모르면 빈 문자열.\n"
        "출력은 JSON 객체만: {\"summary_ko\":\"...\",\"title_ja\":\"...\",\"title_ko\":\"...\"}. 설명 금지.\n\n"
        f"자막 원본:\n{joined}"
    )
    client = _client()
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL, max_tokens=2000, thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        d = _extract_json(msg_text(msg))
    except Exception:
        return {"summary_ko": joined, "title_ja": "", "title_ko": ""}
    return {"summary_ko": (d.get("summary_ko") or "").strip(),
            "title_ja": (d.get("title_ja") or "").strip(),
            "title_ko": (d.get("title_ko") or "").strip()}


def extract(job, video: Path, on_progress=None) -> Tuple[List[Segment], str]:
    """Run Stage 1. Returns (segments, source_lang). Populates seg.text_kr with the
    on-screen source text (any language)."""
    def progress(m):
        if on_progress:
            on_progress(m)

    frames_dir = config.job_dir(job.id) / "frames"
    sheets_dir = config.job_dir(job.id) / "sheets"
    progress("프레임 추출 중...")
    frame_paths = frames_util.extract_frames(video, frames_dir, job.frame_interval)

    client = _client()
    # Use a generous crop that reliably contains the subtitle. Clamp the top so a
    # stale/too-narrow value can never cut the subtitle off (always cover >= 0.45 down).
    eff_top = min(job.crop_top_ratio, 0.45)
    eff_bottom = max(job.crop_bottom_ratio, 0.95)
    job.crop_top_ratio, job.crop_bottom_ratio = eff_top, eff_bottom
    progress("콘택트시트 조립 중...")
    sheets = build_contact_sheets(
        frame_paths, eff_top, eff_bottom, job.frame_interval, sheets_dir
    )
    raw: list = []
    for i, (path, t0, t1) in enumerate(sheets, start=1):
        progress(f"Claude Vision 분석 중... ({i}/{len(sheets)} 시트)")
        try:
            raw.extend(_read_sheet(client, path, t0, t1))
        except Exception as e:  # surface the real error instead of silently continuing
            raise RuntimeError(f"Vision 호출 실패(시트 {i}): {e}")
        # Fail fast: if the first ~half of the video yielded nothing, stop before
        # burning credits on the rest.
        if i >= 6 and len(raw) == 0:
            raise RuntimeError(
                "자막을 찾지 못했습니다. 이 영상에 화면에 박힌(번인) 자막이 있는지 확인하세요. "
                "(자막이 앱/CC로 따로 뜨는 소프트 자막이면 영상 픽셀에 없어 읽을 수 없습니다.)"
            )

    # Order + merge duplicates split across sheet boundaries.
    items = []
    for r in raw:
        try:
            start = round(float(r.get("start")), 3)
            end = round(float(r.get("end")), 3)
        except (TypeError, ValueError):
            continue
        text = (r.get("text") or "").strip()
        if not text or end <= start:
            continue
        items.append((start, end, text, r.get("type", "narration"), r.get("lang", ""),
                      (r.get("text_ko") or "").strip()))
    items.sort(key=lambda x: x[0])

    merged: List[Segment] = []
    langs = {}
    idx = 1
    for (start, end, text, typ, lang, text_ko) in items:
        if merged and _norm(text) == _norm(merged[-1].text_kr) and start <= merged[-1].end + 0.6:
            merged[-1].end = max(merged[-1].end, end)
            merged[-1].recompute_duration()
            continue
        typ = "dialogue" if str(typ).lower().startswith("dial") else "narration"
        merged.append(Segment(
            index=idx, start=start, end=end, duration=round(end - start, 3),
            text_kr=text, text_ko=text_ko, type=typ,
            color="white" if typ == "narration" else "green",
        ))
        idx += 1
        if lang:
            langs[lang] = langs.get(lang, 0) + 1

    source_lang = max(langs, key=langs.get) if langs else ""
    return merged, source_lang
