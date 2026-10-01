"""박스(사각형) 영역을 영상 전체 구간에서 지우는 cv2 인페인팅 엔진.

GPU/torch 불필요(가벼움). 지정한 박스 영역을 매 프레임 cv2.inpaint(TELEA)로 메우고,
원본 오디오를 다시 입혀 mp4로 저장한다. (v2에서 AI 엔진 분기 추가 예정)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Optional

import cv2
import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


def first_frame(src: str, out_jpg: str) -> tuple[int, int]:
    """첫 프레임을 jpg로 저장하고 (가로, 세로) 반환."""
    cap = cv2.VideoCapture(src)
    ok, fr = cap.read()
    cap.release()
    if not ok or fr is None:
        raise RuntimeError("영상 프레임을 읽을 수 없습니다.")
    cv2.imwrite(out_jpg, fr)
    return int(fr.shape[1]), int(fr.shape[0])


def duration(src: str) -> float:
    """영상 길이(초). ffprobe 우선(정확), 실패 시 cv2 추정. 못 구하면 0.0."""
    # 1) ffprobe (프레임카운트/가변프레임레이트에 영향 안 받음)
    try:
        res = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", src],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20,
        )
        val = (res.stdout or "").strip()
        if val:
            d = float(val)
            if d > 0:
                return d
    except Exception:
        pass
    # 2) cv2 폴백
    cap = cv2.VideoCapture(src)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        if fps > 0 and total > 0:
            return float(total) / float(fps)
    finally:
        cap.release()
    return 0.0


def frame_at(src: str, t_sec: float) -> bytes:
    """t초 시점의 프레임을 jpg 바이트로 반환(미리보기용)."""
    cap = cv2.VideoCapture(src)
    try:
        ok, fr = False, None
        if t_sec and t_sec > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t_sec) * 1000.0)
            ok, fr = cap.read()
        if not ok or fr is None:
            # POS_MSEC 실패 시 프레임 인덱스로 폴백
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            idx = int(float(t_sec) * fps) if t_sec and t_sec > 0 else 0
            if total:
                idx = max(0, min(idx, total - 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
        if not ok or fr is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, fr = cap.read()
        if not ok or fr is None:
            raise RuntimeError("프레임을 읽을 수 없습니다.")
        ok2, buf = cv2.imencode(".jpg", fr)
        if not ok2:
            raise RuntimeError("프레임 인코딩 실패.")
        return buf.tobytes()
    finally:
        cap.release()


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


def _mask_bbox(mask: np.ndarray, pad: int) -> Optional[tuple[int, int, int, int]]:
    """마스크(지울 영역)를 감싸는 사각형 범위(여유 pad px 포함). 비어 있으면 None."""
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return None
    h, w = mask.shape
    x1 = max(0, int(xs.min()) - pad)
    y1 = max(0, int(ys.min()) - pad)
    x2 = min(w, int(xs.max()) + 1 + pad)
    y2 = min(h, int(ys.max()) + 1 + pad)
    return x1, y1, x2, y2


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

    # 전체 화면이 아니라 "지울 네모를 감싸는 영역만" inpaint → 대폭 속도 향상.
    pad = radius + 8
    bbox = _mask_bbox(mask, pad)
    x1, y1, x2, y2 = bbox  # bbox는 mask.any()이므로 None 아님
    mask_roi = np.ascontiguousarray(mask[y1:y2, x1:x2])

    def fill(fr: np.ndarray) -> np.ndarray:
        roi = np.ascontiguousarray(fr[y1:y2, x1:x2])
        fr[y1:y2, x1:x2] = cv2.inpaint(roi, mask_roi, radius, cv2.INPAINT_TELEA)
        return fr

    silent = str(Path(out_mp4).with_name("silent.mp4"))
    vw = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not vw.isOpened():
        cap.release()
        raise RuntimeError("출력 영상을 만들 수 없습니다.")

    # cv2.inpaint는 GIL을 풀어 여러 코어로 병렬 처리 가능. 메모리 보호 위해 청크 단위.
    workers = max(1, min(6, (os.cpu_count() or 2)))
    chunk = max(8, workers * 3)
    i = 0
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            while True:
                frames = []
                for _ in range(chunk):
                    ok, fr = cap.read()
                    if not ok:
                        break
                    frames.append(fr)
                if not frames:
                    break
                for out in ex.map(fill, frames):  # 순서 보존
                    vw.write(out)
                i += len(frames)
                if progress:
                    progress(f"{i}/{total} 프레임 지우는 중...")
    finally:
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
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        ok = res.returncode == 0 and Path(out_mp4).exists()
    except FileNotFoundError:
        ok = False  # ffmpeg 미설치 등
    if not ok:
        # ffmpeg 실패/부재 시 무음 영상이라도 결과로 제공
        shutil.copyfile(silent, out_mp4)
    try:
        Path(silent).unlink()
    except OSError:
        pass
