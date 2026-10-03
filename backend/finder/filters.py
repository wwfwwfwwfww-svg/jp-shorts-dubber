"""Duration + language filtering for collected videos.

- <=180s: the API's videoDuration=short only means <4min, so we re-filter on the
  real contentDetails.duration (ISO-8601).
- Exclude Korean/Japanese: drop videos whose defaultAudioLanguage/defaultLanguage
  is ko/ja, OR whose title/description contains Hangul or Hiragana/Katakana.
"""
from __future__ import annotations

import re

_ISO_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
# Hangul syllables/jamo, Hiragana, Katakana (incl. half-width kana).
_KO_JA_CHARS = re.compile(
    r"[가-힣ᄀ-ᇿ㄰-㆏"      # Hangul
    r"぀-ゟ゠-ヿｦ-ﾝ]"       # Hiragana / Katakana
)
# 비(非)타겟 문자: 서구(라틴)·한일(별도 처리) 외 — 인도/동남아/중동/슬라브/중화권 등.
# 이런 제목의 영상은 서구 바이럴이 아니라 재업로드/현지 콘텐츠일 확률이 높아 제외한다.
_NON_TARGET_CHARS = re.compile(
    r"[ऀ-ॿ"   # Devanagari (힌디 등)
    r"ঀ-৿"    # Bengali
    r"਀-ൿ"    # Gurmukhi/Gujarati/Tamil/Telugu/Kannada/Malayalam 등
    r"฀-๿"    # Thai
    r"຀-໿"    # Lao
    r"က-႟"    # Myanmar
    r"؀-ۿݐ-ݿࢠ-ࣿ"  # Arabic
    r"֐-׿"    # Hebrew
    r"Ѐ-ӿ"    # Cyrillic (러시아 등)
    r"一-鿿㐀-䶿"   # CJK Han (중국어 등; 일본어 한자 겹침은 ko/ja가 선처리)
    r"가-힣]"  # (Hangul — ko 중복, 안전차원)
)
# 명시 언어가 영어권/서구가 아니면 제외(일부 영상은 defaultAudioLanguage가 채워져 있음).
_BLOCK_LANGS = {
    "hi", "id", "th", "vi", "ar", "ru", "tr", "bn", "ta", "te", "ur", "fa",
    "zh", "ms", "fil", "tl", "pa", "mr", "gu", "kn", "ml", "my", "km", "lo",
    "ne", "si", "uk", "he", "am",
}
MAX_DURATION_SEC = 180


def parse_duration(iso: str) -> int:
    """ISO-8601 duration (e.g. PT1M5S) -> seconds. Returns 0 if unparseable."""
    if not iso:
        return 0
    m = _ISO_DUR.fullmatch(iso.strip())
    if not m:
        return 0
    days, hours, mins, secs = (int(x) if x else 0 for x in m.groups())
    return days * 86400 + hours * 3600 + mins * 60 + secs


def has_ko_ja_text(*texts: str) -> bool:
    for t in texts:
        if t and _KO_JA_CHARS.search(t):
            return True
    return False


def is_korean_or_japanese(item: dict) -> bool:
    """item = a videos.list resource (with snippet)."""
    snip = item.get("snippet", {})
    for field in ("defaultAudioLanguage", "defaultLanguage"):
        lang = (snip.get(field) or "").lower()
        if lang.startswith("ko") or lang.startswith("ja"):
            return True
    if has_ko_ja_text(snip.get("title", ""), snip.get("description", "")):
        return True
    return False


def is_non_target(item: dict) -> bool:
    """서구(영어권) 바이럴이 아닌 콘텐츠(인도·동남아·중동·러시아·중화권 등)를 제외.

    - 명시 언어가 블록 목록이면 제외.
    - 제목에 비라틴·비(ko/ja) 문자가 일정 비율 이상이면 제외(재업로드/현지 콘텐츠).
    ko/ja는 is_korean_or_japanese가 따로 처리하므로 여기선 추가로 거르지 않아도 됨.
    """
    snip = item.get("snippet", {})
    for field in ("defaultAudioLanguage", "defaultLanguage"):
        lang = (snip.get(field) or "").lower().split("-")[0]
        if lang in _BLOCK_LANGS:
            return True
    title = snip.get("title", "") or ""
    hits = _NON_TARGET_CHARS.findall(title)
    # 제목에 비타겟 문자가 3자 이상이거나, 글자 대비 20% 이상이면 비타겟으로 간주.
    letters = sum(1 for ch in title if ch.isalpha())
    if len(hits) >= 3 or (letters and len(hits) / letters >= 0.2):
        return True
    return False


def duration_ok(item: dict, max_sec: int = MAX_DURATION_SEC) -> bool:
    secs = parse_duration(item.get("contentDetails", {}).get("duration", ""))
    return 0 < secs <= max_sec
