"""제작(자막교체) 라우터 — /api/produce 마운트."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from . import pipeline, render, store
from .models import (BandUpdate, FromFinderRequest, ProduceJob, SegmentsUpdate)

router = APIRouter(prefix="/api/produce", tags=["produce"])

FINDER_WORK = config.DATA_DIR / "finder_work"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    job_id = _new_id()
    d = store.job_dir(job_id)
    dest = d / "source.mp4"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    job = ProduceJob(id=job_id, source_path=str(dest), origin="upload",
                     title=(file.filename or "").rsplit(".", 1)[0], status="created",
                     message="업로드 완료 — 자막 인식을 시작하세요.")
    store.save(job)
    return job


@router.post("/from_finder")
def from_finder(req: FromFinderRequest):
    src_dir = FINDER_WORK / req.video_id
    files = sorted(src_dir.glob("source.*")) if src_dir.exists() else []
    if not files:
        raise HTTPException(404, "먼저 소재 찾기에서 '작업하기'로 영상을 다운로드하세요.")
    job_id = _new_id()
    job = ProduceJob(id=job_id, source_path=str(files[0]), origin="finder",
                     title=req.video_id, status="created",
                     message="소재를 불러왔습니다 — 자막 인식을 시작하세요.")
    store.save(job)
    return job


@router.post("/{job_id}/analyze")
def analyze(job_id: str, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY가 필요합니다(자막 인식에 Claude Vision 사용).")
    background.add_task(pipeline.analyze, job_id)
    return {"ok": True}


@router.post("/{job_id}/translate")
def translate(job_id: str, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY가 필요합니다.")
    background.add_task(pipeline.translate, job_id)
    return {"ok": True}


@router.patch("/{job_id}/segments")
def patch_segments(job_id: str, upd: SegmentsUpdate):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    by_index = {s.index: s for s in job.segments}
    for e in upd.segments:
        seg = by_index.get(e.index)
        if seg is None:
            continue
        if e.text_kr is not None:
            seg.text_kr = e.text_kr
        if e.text_ja is not None:
            seg.text_ja = e.text_ja
        if e.start is not None:
            seg.start = round(float(e.start), 3)
        if e.end is not None:
            seg.end = round(float(e.end), 3)
        seg.recompute_duration()
    store.save(job)
    return job


@router.put("/{job_id}/band")
def set_band(job_id: str, upd: BandUpdate):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    for field, val in upd.model_dump(exclude_none=True).items():
        setattr(job, field, val)
    store.save(job)
    return job


@router.post("/{job_id}/render")
def do_render(job_id: str, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    if not any(s.text_ja for s in job.segments):
        raise HTTPException(400, "먼저 일본어 번역을 완료하세요.")
    background.add_task(render.render, job_id)
    return {"ok": True}


@router.get("/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return job


@router.get("/{job_id}/source")
def get_source(job_id: str):
    job = store.get(job_id)
    if job is None or not Path(job.source_path).exists():
        raise HTTPException(404, "원본을 찾을 수 없습니다.")
    return FileResponse(job.source_path, media_type="video/mp4")


@router.get("/{job_id}/output")
def get_output(job_id: str):
    job = store.get(job_id)
    if job is None or not job.output_file or not Path(job.output_file).exists():
        raise HTTPException(404, "결과 영상이 아직 없습니다.")
    return FileResponse(job.output_file, media_type="video/mp4")


@router.get("/{job_id}/download")
def download_output(job_id: str):
    job = store.get(job_id)
    if job is None or not job.output_file or not Path(job.output_file).exists():
        raise HTTPException(404, "결과 영상이 아직 없습니다.")
    name = (job.title or job_id) + "_JP.mp4"
    return FileResponse(job.output_file, media_type="video/mp4", filename=name)
