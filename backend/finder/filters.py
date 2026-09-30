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


def duration_ok(item: dict, max_sec: int = MAX_DURATION_SEC) -> bool:
    secs = parse_duration(item.get("contentDetails", {}).get("duration", ""))
    return 0 < secs <= max_sec
