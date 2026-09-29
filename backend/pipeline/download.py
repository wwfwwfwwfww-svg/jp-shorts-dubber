"""Input handling: fetch from URL (yt-dlp), probe media metadata (ffprobe)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from .. import config
from ..models import VideoMeta


def probe_media(path: Path) -> VideoMeta:
    """Read duration / resolution / fps using ffprobe."""
    cmd = [
        config.FFPROBE_CMD,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()}")
    info = json.loads(out.stdout or "{}")

    meta = VideoMeta()
    fmt = info.get("format", {})
    try:
        meta.duration = float(fmt.get("duration", 0.0) or 0.0)
    except (TypeError, ValueError):
        meta.duration = 0.0

    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            meta.width = int(s.get("width", 0) or 0)
            meta.height = int(s.get("height", 0) or 0)
            meta.fps = _parse_fps(s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/0")
            break
    return meta


def _parse_fps(rate: str) -> float:
    try:
        num, den = rate.split("/")
        den_f = float(den)
        return round(float(num) / den_f, 3) if den_f else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def download_url(url: str, dest_dir: Path) -> tuple[Path, str]:
    """Download a video via yt-dlp into dest_dir. Returns (path, title)."""
    from yt_dlp import YoutubeDL  # imported here so the app still starts without it

    out_tmpl = str(dest_dir / "source.%(ext)s")
    ydl_opts = {
        "outtmpl": out_tmpl,
        "format": "mp4/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "") if isinstance(info, dict) else ""

    # Find the produced file (prefer source.mp4).
    candidate = dest_dir / "source.mp4"
    if candidate.exists():
        return candidate, title
    files = sorted(dest_dir.glob("source.*"))
    if not files:
        raise RuntimeError("yt-dlp finished but no output file was found.")
    return files[0], title
