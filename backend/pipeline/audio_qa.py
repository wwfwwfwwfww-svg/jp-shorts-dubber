"""Stage 3 automatic audio QA — pure signal processing (numpy + soundfile).

Checks the concatenated, normalized track:
  - speech-region count vs expected segment count (RMS energy gating)
  - clipping (|amplitude| > 0.99)
  - peak level near the normalization target
  - overlap: structurally impossible with sequential concat (reported as info)
Returns a human-readable checklist for the UI.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .. import config


def _mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        data = data.mean(axis=1)
    return data.astype(np.float64)


def _speech_regions(x: np.ndarray, sr: int) -> int:
    """Count contiguous speech regions via RMS gating."""
    win = max(1, int(sr * 0.03))       # 30 ms
    hop = max(1, int(sr * 0.01))       # 10 ms
    if len(x) < win:
        return 0
    rms = []
    for i in range(0, len(x) - win, hop):
        frame = x[i:i + win]
        rms.append(float(np.sqrt(np.mean(frame * frame))))
    rms = np.array(rms)
    if rms.max() <= 0:
        return 0
    thr = max(0.02, 0.12 * rms.max())
    voiced = rms > thr
    # merge gaps shorter than ~0.2s (20 hops)
    regions, run, gap = 0, False, 0
    for v in voiced:
        if v:
            if not run:
                regions += 1
                run = True
            gap = 0
        else:
            gap += 1
            if gap > 20:
                run = False
    return regions


def run_qa(job, combined_wav: Path) -> dict:
    checks = []

    def add(ok, label, detail=""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})

    expected = sum(1 for s in job.segments if s.audio_file)
    try:
        data, sr = sf.read(str(combined_wav))
    except Exception as e:  # noqa: BLE001
        add(False, "오디오 파일 로드", str(e))
        return {"checks": checks, "ok": False}

    x = _mono(data)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    peak_db = 20 * np.log10(peak) if peak > 0 else float("-inf")

    regions = _speech_regions(x, sr)
    add(regions >= max(1, int(expected * 0.5)),
        "발화 구간 감지",
        f"감지 {regions}개 / 세그먼트 {expected}개 (문장 내 쉼으로 수는 다를 수 있음)")

    clipped = int(np.sum(np.abs(x) > 0.99)) if len(x) else 0
    add(clipped == 0, "클리핑(진폭>0.99) 없음", f"{clipped} 샘플")

    add(-6.0 <= peak_db <= 0.0,
        f"피크 음량 정규화(목표 {config.TARGET_PEAK_DB}dB)",
        f"측정 {peak_db:.2f} dBFS")

    add(True, "구간 겹침 없음", "순차 연결 방식이라 구조적으로 겹침 없음")

    # Length match: actual dub vs the narration span Stage 2 aimed for (A4).
    actual = round(len(x) / sr, 2) if sr else 0.0
    target = round(job.target_seconds or job.active_seconds or 0.0, 2)
    if target > 0:
        drift = actual - target
        pct = drift / target * 100
        add(abs(pct) <= 5.0,
            "길이 정합(목표 대비)",
            f"목표 {target:.1f}s · 실제 {actual:.1f}s · 차이 {drift:+.1f}s ({pct:+.1f}%)")

    return {"checks": checks, "ok": all(c["ok"] for c in checks),
            "duration": actual, "target": target}
