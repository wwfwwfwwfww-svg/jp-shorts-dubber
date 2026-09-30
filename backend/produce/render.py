"""ffmpeg 렌더: 원본 영어 자막 띠 가리기 + 일본어 자막 번인 + 원본 소리 유지.

리눅스 컨테이너엔 ffmpeg가 없어 실제 실행은 사용자 환경(윈도우)에서 이뤄진다.
명령 문자열은 단순·견고하게 구성한다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from .. import config
from ..models import Segment
from ..pipeline import download
from . import subtitle_ass, store


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def build_ffmpeg_cmd(source: Path, ass_name: str, out: Path, *,
                     band_top: float, band_bottom: float, cover_mode: str,
                     cover_opacity: float) -> list:
    """소스(절대경로) + sub.ass(작업폴더 상대) → 결과 mp4 명령. cwd=작업폴더로 실행."""
    bt = _clamp(band_top, 0.0, 0.98)
    bb = _clamp(band_bottom, bt + 0.02, 1.0)
    bh = bb - bt
    op = _clamp(cover_opacity, 0.0, 1.0)

    ff = config.FFMPEG_CMD
    base = [ff, "-y", "-i", str(source)]
    venc = ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p"]

    if cover_mode == "blur":
        fc = (
            f"[0:v]split=2[base][t];"
            f"[t]crop=iw:ih*{bh:.4f}:0:ih*{bt:.4f},boxblur=24:2[bl];"
            f"[base][bl]overlay=0:ih*{bt:.4f},subtitles={ass_name}[v]"
        )
        return base + ["-filter_complex", fc, "-map", "[v]", "-map", "0:a?"] + venc + \
            ["-c:a", "copy", str(out)]

    # box (기본): 어두운 반투명 띠로 원본 자막을 덮고 그 위에 일본어 자막
    vf = (f"drawbox=x=0:y=ih*{bt:.4f}:w=iw:h=ih*{bh:.4f}:color=black@{op:.2f}:t=fill,"
          f"subtitles={ass_name}")
    return base + ["-vf", vf] + venc + ["-c:a", "copy", str(out)]


def render(job_id: str) -> None:
    from .models import ProduceJob  # local to avoid cycles
    job = store.get(job_id)
    if job is None:
        return
    try:
        job.status = "rendering"
        job.message = "렌더링 준비 중..."
        job.error = ""
        store.save(job)

        segments: List[Segment] = job.segments
        # 해상도 확보(메타에 없으면 프로브)
        w, h = job.meta.width, job.meta.height
        if not (w and h):
            meta = download.probe_media(Path(job.source_path))
            job.meta = meta
            w, h = meta.width, meta.height

        d = store.job_dir(job_id)
        ass = subtitle_ass.build_ass(
            segments, w, h, job.band_top, job.band_bottom,
            font_name=job.font_name, font_scale=job.font_scale)
        (d / "sub.ass").write_text(ass, encoding="utf-8")

        out = d / "output.mp4"
        cmd = build_ffmpeg_cmd(
            Path(job.source_path).resolve(), "sub.ass", out.resolve(),
            band_top=job.band_top, band_bottom=job.band_bottom,
            cover_mode=job.cover_mode, cover_opacity=job.cover_opacity)

        job.message = "ffmpeg 렌더링 중... (영상 길이에 따라 수십 초~수 분)"
        store.save(job)
        res = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if res.returncode != 0 or not out.exists():
            raise RuntimeError(f"ffmpeg 실패: {res.stderr[-800:]}")

        job.output_file = str(out)
        job.status = "done"
        job.message = "완료 — 결과 영상을 확인하세요."
        store.save(job)
    except Exception as e:
        job = store.get(job_id) or job
        job.status = "error"
        job.error = str(e)
        job.message = f"오류: {e}"
        store.save(job)
