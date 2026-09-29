"""Central configuration. Loads .env (if present) and exposes typed settings.

Paths, tuning thresholds and API keys all live here so the rest of the code
never reads os.environ directly.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains "backend/".
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- Directories ---
DATA_DIR = ROOT_DIR / "data"
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR.mkdir(exist_ok=True)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


# --- External tools ---
# tesseract.exe: explicit path from .env, else whatever is on PATH.
TESSERACT_CMD = _get_str("TESSERACT_CMD") or (shutil.which("tesseract") or "")
# ffmpeg / ffprobe are expected on PATH.
FFMPEG_CMD = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_CMD = shutil.which("ffprobe") or "ffprobe"

# --- Stage 1: frame sampling + subtitle crop + contact sheets ---
FRAME_INTERVAL = _get_float("FRAME_INTERVAL", 0.5)   # seconds between sampled frames (fps=2)
# Cover the lower HALF of the frame — subtitles in shorts sit anywhere from mid
# screen to the bottom (varies by creator). A generous band catches them all.
CROP_TOP_RATIO = _get_float("CROP_TOP_RATIO", 0.4)   # keep from this y-ratio downward
CROP_BOTTOM_RATIO = _get_float("CROP_BOTTOM_RATIO", 1.0)
# 4 cols x 4 rows = 16 frames/sheet. Taller crop -> fewer rows so the sheet stays
# <= ~1568px on both sides (no Claude Vision downscale, text stays readable).
CONTACT_COLS = int(_get_float("CONTACT_COLS", 4))    # frames per contact-sheet row
CONTACT_ROWS = int(_get_float("CONTACT_ROWS", 4))    # rows per contact sheet
CONTACT_CELL_W = int(_get_float("CONTACT_CELL_W", 384))  # px width of each cell

# --- Stage 2: Japanese length budget ---
# Measured from real ElevenLabs output (this voice, 3 jobs): ~6.0 chars/sec at
# speed 1.0. Was 6.36 (guess) which overestimated the rate and made dubs run long.
NATURAL_CHARS_PER_SEC = _get_float("NATURAL_CHARS_PER_SEC", 6.0)
# Budget target range: Stage 2 aims for enough Japanese text to speak at this pace.
TARGET_SPEED_MIN = _get_float("TARGET_SPEED_MIN", 1.10)
TARGET_SPEED_MAX = _get_float("TARGET_SPEED_MAX", 1.18)
# Final-speed clamp floor. If the script comes up short, we slow toward 1.0 (normal
# speed) to fill the video length, rather than leaving the dub short. Never below 1.0
# (that felt sluggish). Ceiling is TARGET_SPEED_MAX.
SPEED_FLOOR = _get_float("SPEED_FLOOR", 1.0)
MAX_CHARS_PER_SEGMENT = int(_get_float("MAX_CHARS_PER_SEGMENT", 26))

# --- Stage 3: loudness ---
TARGET_PEAK_DB = _get_float("TARGET_PEAK_DB", -1.0)

# --- APIs ---
ANTHROPIC_API_KEY = _get_str("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _get_str("ANTHROPIC_MODEL", "claude-sonnet-5")
# Cheap/fast model for the 소재 찾기 tab (category classification, keyword
# extraction, JP translation for the "일본 미진출" check). Never used by the
# dubbing pipeline, which keeps ANTHROPIC_MODEL.
ANTHROPIC_MODEL_CHEAP = _get_str("ANTHROPIC_MODEL_CHEAP", "claude-haiku-4-5")
ELEVENLABS_API_KEY = _get_str("ELEVENLABS_API_KEY")
ELEVEN_VOICE_ID = _get_str("ELEVEN_VOICE_ID")
ELEVEN_MODEL = _get_str("ELEVEN_MODEL", "eleven_multilingual_v2")

# --- 소재 찾기 (finder) tab ---
# The finder keeps its own SQLite DB and settings; these are only the INITIAL
# defaults / secrets read from .env. Most are editable at runtime in the UI
# (stored in data/finder.db → settings table), which overrides these.
FINDER_DB = DATA_DIR / "finder.db"
YOUTUBE_API_KEY = _get_str("YOUTUBE_API_KEY")
TELEGRAM_BOT_TOKEN = _get_str("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get_str("TELEGRAM_CHAT_ID")

FINDER_VIEW_FLOOR = int(_get_float("FINDER_VIEW_FLOOR", 3_000_000))   # 조회수 하한 기본 300만
FINDER_PER_KEYWORD = int(_get_float("FINDER_PER_KEYWORD", 50))        # 키워드당 수집량 (최대 100)
FINDER_PERIOD_DAYS = int(_get_float("FINDER_PERIOD_DAYS", 14))        # 기본 검색 기간 2주
FINDER_REGIONS = [r.strip().upper() for r in
                  _get_str("FINDER_REGIONS",
                           "US,GB,CA,AU,DE,FR,ES,BR,MX,ID").split(",") if r.strip()]
FINDER_SCAN_HOURS = int(_get_float("FINDER_SCAN_HOURS", 6))           # 레퍼런스 채널 자동 스캔 주기
FINDER_MORNING_HOUR = int(_get_float("FINDER_MORNING_HOUR", 7))       # 아침 자동수집 시각
FINDER_QUOTA_LIMIT = int(_get_float("FINDER_QUOTA_LIMIT", 10_000))    # YouTube Data API 일일 한도
FINDER_JAPAN_CHECK_TOP_N = int(_get_float("FINDER_JAPAN_CHECK_TOP_N", 20))


# Set by start.bat so the server opens the browser itself (avoids fragile
# browser-launching from the batch file).
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "").strip() == "1"


def tesseract_available() -> bool:
    if not TESSERACT_CMD:
        return False
    # An explicit path must exist; a bare command name is assumed to be on PATH.
    if os.sep in TESSERACT_CMD or "/" in TESSERACT_CMD:
        return Path(TESSERACT_CMD).exists()
    return True


def job_dir(job_id: str) -> Path:
    d = DATA_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d
