"""Frame sampling + subtitle-band cropping (no OCR).

Shared by the Stage-1 vision pipeline. Frames are sampled at a fixed interval
(fps = 1/interval) and each frame's bottom subtitle band is cropped.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

import cv2
import numpy as np

from .. import config


def extract_frames(video: Path, frames_dir: Path, interval: float) -> List[Path]:
    """Sample frames every `interval` seconds → frame_00001.png ... Returns paths.
    Frame k (1-based) corresponds to time ~ (k-1) * interval."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.png"):
        old.unlink()
    fps = 1.0 / interval if interval > 0 else 2.0
    cmd = [
        config.FFMPEG_CMD, "-y", "-i", str(video),
        "-vf", f"fps={fps}",
        "-q:v", "2",
        str(frames_dir / "frame_%05d.png"),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed: {res.stderr[-500:]}")
    return sorted(frames_dir.glob("frame_*.png"))


def frame_time(index0: int, interval: float) -> float:
    """Timestamp (seconds) of the 0-based sampled frame index."""
    return round(index0 * interval, 3)


def crop_band(img: np.ndarray, top_ratio: float, bottom_ratio: float) -> np.ndarray:
    """Crop the horizontal band where burned-in subtitles sit (bottom of frame)."""
    h = img.shape[0]
    y0 = max(0, int(h * top_ratio))
    y1 = min(h, int(h * bottom_ratio))
    if y1 <= y0:
        y0, y1 = int(h * 0.68), h
    return img[y0:y1, :]
