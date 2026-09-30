"""제작(자막교체) 오케스트레이션 — 분석(Vision) → 번역 → (렌더는 render.py).

기존 pipeline.vision.extract / frames / download.probe_media 를 그대로 재사용한다.
"""
from __future__ import annotations

from pathlib import Path

from ..pipeline import download, vision
from . import store, translate_sub


def _progress(job):
    def cb(msg):
        job.message = msg
        store.save(job)
    return cb


def analyze(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        job.status = "analyzing"
        job.message = "영상 분석 준비 중..."
        job.error = ""
        store.save(job)

        # 해상도 등 메타(가릴 띠 미리보기·렌더에 필요)
        try:
            job.meta = download.probe_media(Path(job.source_path))
        except Exception:
            pass

        segs, lang = vision.extract(job, Path(job.source_path), on_progress=_progress(job))
        job.segments = segs
        job.source_lang = lang
        job.status = "analyzed"
        job.message = f"자막 {len(segs)}구간 인식 완료 — 확인 후 번역하세요."
        store.save(job)
    except Exception as e:
        job = store.get(job_id) or job
        job.status = "error"
        job.error = str(e)
        job.message = f"오류: {e}"
        store.save(job)


def translate(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        job.status = "translating"
        job.message = "일본어 자막 번역 중..."
        job.error = ""
        store.save(job)
        translate_sub.translate(job.segments)
        job.status = "translated"
        job.message = "번역 완료 — 자막·가릴 띠를 확인하고 렌더하세요."
        store.save(job)
    except Exception as e:
        job = store.get(job_id) or job
        job.status = "error"
        job.error = str(e)
        job.message = f"오류: {e}"
        store.save(job)
