"""박스(사각형) 영역을 영상 전체 구간에서 지우는 cv2 인페인팅 엔진.

GPU/torch 불필요(가벼움). 지정한 박스 영역을 매 프레임 cv2.inpaint(TELEA)로 메우고,
원본 오디오를 다시 입혀 mp4로 저장한다. (v2에서 AI 엔진 분기 추가 예정)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, List, Optional

import cv2
import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def first_frame(src: str, out_jpg: str) -> tuple[int, int]:
    """첫 프레임을 jpg로 저장하고 (가로, 세로) 반환."""
    cap = cv2.VideoCapture(src)
    ok, fr = cap.read()
    cap.release()
    if not ok or fr is None:
        raise RuntimeError("영상 프레임을 읽을 수 없습니다.")
    cv2.imwrite(out_jpg, fr)
    return int(fr.shape[1]), int(fr.shape[0])


def build_mask(w: int, h: int, boxes: List[dict]) -> np.ndarray:
    """비율 좌표 박스들 → 흑백 마스크(지울 영역=흰색). 가장자리 살짝 확장."""
    m = np.zeros((h, w), np.uint8)
    for b in boxes:
        x = max(0, int(float(b["x"]) * w))
        y = max(0, int(float(b["y"]) * h))
        x2 = min(w, x + int(float(b["w"]) * w))
        y2 = min(h, y + int(float(b["h"]) * h))
        if x2 > x and y2 > y:
            m[y:y2, x:x2] = 255
    if m.any():
        m = cv2.dilate(m, np.ones((5, 5), np.uint8), iterations=1)
    return m


def process(src: str, out_mp4: str, boxes: List[dict], radius: int = 6,
            progress: Optional[Callable[[str], None]] = None) -> None:
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError("영상을 열 수 없습니다.")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    mask = build_mask(w, h, boxes)
    if not mask.any():
        cap.release()
        raise RuntimeError("지울 영역이 없습니다. 박스를 지정하세요.")
    radius = max(1, min(30, int(radius)))

    silent = str(Path(out_mp4).with_name("silent.mp4"))
    vw = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not vw.isOpened():
        cap.release()
        raise RuntimeError("출력 영상을 만들 수 없습니다.")

    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        out = cv2.inpaint(fr, mask, radius, cv2.INPAINT_TELEA)
        vw.write(out)
        i += 1
        if progress and i % 15 == 0:
            progress(f"{i}/{total} 프레임 지우는 중...")
    cap.release()
    vw.release()
    if i == 0:
        raise RuntimeError("처리된 프레임이 없습니다.")

    # 원본 오디오를 다시 입혀서 최종 mp4(h264, 브라우저 호환)
    if progress:
        progress("오디오 합치고 마무리 중...")
    cmd = [FFMPEG, "-y", "-i", silent, "-i", src,
           "-map", "0:v:0", "-map", "1:a:0?",
           "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", out_mp4]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not Path(out_mp4).exists():
        # ffmpeg 실패 시 무음 영상이라도 결과로 제공
        shutil.copyfile(silent, out_mp4)
    try:
        Path(silent).unlink()
    except OSError:
        pass
