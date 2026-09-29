"""FastAPI app: 4-stage automated dubbing pipeline + static frontend.

Stages (each behind a human gate; paid steps never auto-run):
  1 extract  : Claude Vision reads on-screen subtitles (Korean/English)
  2 translate: Claude rewrites the story into Japanese (single speed, char budget)
  3 tts      : ElevenLabs TTS -> sequential concat -> normalize -> QA
  4 metadata : titles/thumbnail/description/tags + JP/KR SRT
"""
from __future__ import annotations

import re
import shutil
import threading
import traceback
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, store
from .finder import db as finder_db
from .finder.routes import router as finder_router
from .models import Job, SegmentsUpdate, VideoMeta
from .pipeline import (assemble, audio_qa, download, import_parse, metadata_gen,
                       translate, tts, vision)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ImportRequest(BaseModel):
    text: str
    title: Optional[str] = ""


class TtsRequest(BaseModel):
    voice_id: Optional[str] = ""
    speed: Optional[float] = None   # overrides job.speed if given


class RegenRequest(BaseModel):
    text_ja: Optional[str] = None
    voice_id: Optional[str] = ""


def _safe_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    return name[:80].strip("._ ") or ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        finder_db.init_db()          # 소재 찾기 탭용 SQLite 준비(기존 잡 스토어와 분리)
    except Exception:
        pass                          # 파인더 초기화 실패가 더빙 파이프라인을 막지 않도록
    if config.OPEN_BROWSER:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:8000")).start()
    yield


app = FastAPI(title="JP Shorts Dubber", lifespan=lifespan)
app.include_router(finder_router)


@app.middleware("http")
async def no_cache(request, call_next):
    """Never let the browser cache the frontend, so code updates always apply."""
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


def _progress(job: Job):
    def fn(msg: str) -> None:
        job.message = msg
        store.save(job)
    return fn


def _fail(job_id: str, e: Exception):
    job = store.get(job_id)
    if job:
        job.status = "error"
        job.message = f"{type(e).__name__}: {e}"
        store.save(job)
    traceback.print_exc()


def _resolve_voice(voice_id: str) -> str:
    voice_id = (voice_id or config.ELEVEN_VOICE_ID or "").strip()
    if not voice_id:
        try:
            voices = tts.list_voices()
            voice_id = voices[0]["voice_id"] if voices else ""
        except Exception:
            voice_id = ""
    return voice_id


# --------------------------------------------------------------------------- #
# Upload (free) — download + probe only, then wait at a gate
# --------------------------------------------------------------------------- #
def _run_ingest(job_id: str, source_kind: str, url: Optional[str]) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        jdir = config.job_dir(job_id)
        if source_kind == "url":
            job.status = "downloading"; job.message = "동영상 다운로드 중..."; store.save(job)
            video, title = download.download_url(url or "", jdir)
            job.meta.title = title
        else:
            video = jdir / "source.mp4"
            if not video.exists():
                ups = [p for p in jdir.glob("source.*") if p.suffix != ".json"]
                if not ups:
                    raise RuntimeError("업로드된 파일을 찾을 수 없습니다.")
                video = ups[0]
        meta = download.probe_media(video)
        meta.source = source_kind
        meta.title = job.meta.title or meta.title
        job.meta = meta
        job.status = "uploaded"
        job.message = f"업로드 완료 · 길이 {meta.duration:.1f}s · '분석 시작'을 누르세요"
        store.save(job)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, e)


@app.post("/api/jobs")
async def create_job(
    background: BackgroundTasks,
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    crop_top_ratio: float = Form(config.CROP_TOP_RATIO),
    crop_bottom_ratio: float = Form(config.CROP_BOTTOM_RATIO),
    frame_interval: float = Form(config.FRAME_INTERVAL),
):
    if not url and file is None:
        raise HTTPException(400, "URL 또는 파일 중 하나를 입력하세요.")
    job_id = uuid.uuid4().hex[:12]
    jdir = config.job_dir(job_id)
    source_kind = "url"
    if file is not None:
        source_kind = "upload"
        suffix = Path(file.filename or "source.mp4").suffix or ".mp4"
        dest = jdir / f"source{suffix}"
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    job = Job(id=job_id, status="created",
              crop_top_ratio=crop_top_ratio, crop_bottom_ratio=crop_bottom_ratio,
              frame_interval=frame_interval, meta=VideoMeta(source=source_kind))
    store.save(job)
    background.add_task(_run_ingest, job_id, source_kind, url)
    return {"id": job_id, "status": job.status}


# --------------------------------------------------------------------------- #
# Stage 1 — Claude Vision (paid)
# --------------------------------------------------------------------------- #
def _run_extract(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        jdir = config.job_dir(job_id)
        video = next((p for p in jdir.glob("source.*") if p.suffix != ".json"), None)
        if video is None:
            raise RuntimeError("원본 영상을 찾을 수 없습니다.")
        job.status = "extracting"; store.save(job)
        segs, lang = vision.extract(job, video, on_progress=_progress(job))
        if not segs:
            job.status = "error"
            job.message = ("자막을 찾지 못했습니다. 자막이 화면 하단 절반(크롭 영역)에 있는지 확인하고 "
                           "'고급'에서 크롭 시작값을 낮춰 다시 시도하세요(예: 0.4).")
            store.save(job)
            return
        job.segments = segs
        job.source_lang = lang
        _progress(job)("줄거리 요약 생성 중...")
        try:
            summ = vision.summarize_story(segs)
            job.summary_ko = summ.get("summary_ko", "")
            job.title_ja = summ.get("title_ja", "")
            job.title_ko = summ.get("title_ko", "")
        except Exception:
            pass  # summary is best-effort; extraction already succeeded
        job.status = "stage1_ready"
        title = job.title_ko or job.title_ja
        job.message = f"1단계 완료 · 구간 {len(segs)}개 · 언어 {lang or '?'}" + (f" · 추정 제목: {title}" if title else "")
        store.save(job)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, e)


@app.post("/api/jobs/{job_id}/extract")
async def extract_job(job_id: str, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY가 없습니다. 1단계(Claude Vision 분석)에 필요합니다.")
    job.status = "extracting"; job.message = "분석 대기 중..."; store.save(job)
    background.add_task(_run_extract, job_id)
    return {"id": job_id, "status": "extracting"}


# --------------------------------------------------------------------------- #
# Stage 2 — Japanese reconstruction (paid)
# --------------------------------------------------------------------------- #
def _run_translate(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        job.status = "translating"; store.save(job)
        translate.translate_story(job, on_progress=_progress(job))
        job.status = "stage2_ready"
        job.message = (f"2단계 완료 · 구간 {len(job.segments)}개 · 배속 x{job.speed} · "
                       f"{job.char_actual}자 (목표 {job.char_target_min}~{job.char_target_max})")
        store.save(job)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, e)


@app.post("/api/jobs/{job_id}/translate")
async def translate_job(job_id: str, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not job.segments:
        raise HTTPException(400, "구간이 없습니다.")
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY가 없습니다. 2단계(일본어 변환)에 필요합니다.")
    job.status = "translating"; job.message = "일본어 변환 대기 중..."; store.save(job)
    background.add_task(_run_translate, job_id)
    return {"id": job_id, "status": "translating"}


@app.get("/api/jobs/{job_id}/speed_preview")
async def speed_preview(job_id: str):
    """Recompute char count + implied single speed from current text_ja (for live UI)."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    active = translate.active_seconds(job.segments) or 1.0
    total = sum(translate.count_chars(s.text_ja) for s in job.segments)
    raw = total / (active * config.NATURAL_CHARS_PER_SEC) if active else 1.0
    speed = round(min(config.TARGET_SPEED_MAX, max(config.SPEED_FLOOR, raw)), 3)
    est_seconds = round(total / (config.NATURAL_CHARS_PER_SEC * speed), 1) if speed else 0.0
    return {"char_actual": total, "active_seconds": active, "speed": speed,
            "est_seconds": est_seconds,
            "speed_min": config.SPEED_FLOOR, "speed_max": config.TARGET_SPEED_MAX,
            "char_target_min": job.char_target_min, "char_target_max": job.char_target_max}


# --------------------------------------------------------------------------- #
# Stage 3 — TTS + sequential concat + normalize + QA (paid)
# --------------------------------------------------------------------------- #
def _finalize_audio(job: Job, audio_dir: Path, out_dir: Path, progress) -> None:
    progress("순차 연결 + 음량 정규화 중...")
    wav, _mp3 = assemble.build_sequential(job, audio_dir, out_dir)
    assemble.build_srt(job, out_dir)
    assemble.zip_outputs(job, audio_dir, out_dir)
    job.status = "qa"; progress("오디오 QA 중...")
    job.qa = audio_qa.run_qa(job, wav)


def _run_tts(job_id: str, voice_id: str, speed: float) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        audio_dir = config.job_dir(job_id) / "audio"
        out_dir = config.job_dir(job_id) / "outputs"
        job.status = "dubbing"; job.voice_id = voice_id; job.speed = round(float(speed), 3)
        store.save(job)
        tts.dub_all(job.segments, audio_dir, voice_id, config.ELEVEN_MODEL,
                    speed=job.speed, on_progress=_progress(job))
        _finalize_audio(job, audio_dir, out_dir, _progress(job))
        job.status = "stage3_ready"
        job.message = f"3단계 완료 · 배속 x{job.speed} · {len(job.segments)}구간"
        store.save(job)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, e)


@app.post("/api/jobs/{job_id}/tts")
async def tts_job(job_id: str, payload: TtsRequest, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not any(s.text_ja for s in job.segments):
        raise HTTPException(400, "일본어 텍스트가 없습니다. 먼저 2단계를 실행하세요.")
    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(400, "ELEVENLABS_API_KEY가 없습니다. 3단계(TTS)에 필요합니다.")
    voice_id = _resolve_voice(payload.voice_id)
    if not voice_id:
        raise HTTPException(400, "사용할 ElevenLabs voice_id를 지정하세요 (.env ELEVEN_VOICE_ID).")
    speed = payload.speed if payload.speed else (job.speed or 1.0)
    job.status = "dubbing"; job.message = "TTS 생성 대기 중..."; store.save(job)
    background.add_task(_run_tts, job_id, voice_id, speed)
    return {"id": job_id, "status": "dubbing", "voice_id": voice_id, "speed": speed}


def _run_regen(job_id: str, index: int, text_ja: Optional[str], voice_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        seg = next((s for s in job.segments if s.index == index), None)
        if seg is None:
            raise RuntimeError("구간을 찾을 수 없습니다.")
        if text_ja is not None:
            seg.text_ja = text_ja
        audio_dir = config.job_dir(job_id) / "audio"
        out_dir = config.job_dir(job_id) / "outputs"
        job.status = "dubbing"; job.message = f"#{index} 재생성 중..."; store.save(job)
        path = audio_dir / f"seg_{seg.index:03d}.mp3"
        dur = tts.synth(seg.text_ja or seg.text_kr, path, voice_id, config.ELEVEN_MODEL, speed=job.speed)
        seg.audio_file = path.name
        seg.audio_duration = round(dur, 3)
        seg.speed = job.speed
        _finalize_audio(job, audio_dir, out_dir, _progress(job))  # re-concat all (free), re-QA
        job.status = "stage3_ready"
        job.message = f"#{index} 재생성 완료 · 배속 x{job.speed}"
        store.save(job)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, e)


@app.post("/api/jobs/{job_id}/segment/{index}/regenerate")
async def regenerate_segment(job_id: str, index: int, payload: RegenRequest, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(400, "ELEVENLABS_API_KEY가 없습니다.")
    voice_id = _resolve_voice(payload.voice_id or job.voice_id)
    job.status = "dubbing"; store.save(job)
    background.add_task(_run_regen, job_id, index, payload.text_ja, voice_id)
    return {"id": job_id, "status": "dubbing"}


# --------------------------------------------------------------------------- #
# Stage 4 — metadata + final SRT (paid)
# --------------------------------------------------------------------------- #
def _run_metadata(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        job.status = "generating_meta"; job.message = "메타데이터 생성 중..."; store.save(job)
        job.metadata = metadata_gen.generate_metadata(
            job.segments, title=(job.title_ko or job.title_ja or ""))
        # ensure SRTs reflect the latest audio timeline
        assemble.build_srt(job, config.job_dir(job_id) / "outputs")
        job.status = "done"
        job.message = "4단계 완료 · 메타데이터 + SRT 생성됨"
        store.save(job)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, e)


@app.post("/api/jobs/{job_id}/metadata")
async def metadata_job(job_id: str, background: BackgroundTasks):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY가 없습니다. 4단계(메타데이터)에 필요합니다.")
    if not any(s.text_ja for s in job.segments):
        raise HTTPException(400, "먼저 일본어 변환을 실행하세요.")
    job.status = "generating_meta"; job.message = "대기 중..."; store.save(job)
    background.add_task(_run_metadata, job_id)
    return {"id": job_id, "status": "generating_meta"}


# --------------------------------------------------------------------------- #
# Backup: paste finished Japanese (with timing) -> straight to Stage 3
# --------------------------------------------------------------------------- #
@app.post("/api/jobs/import_ja")
async def import_ja_job(payload: ImportRequest):
    segs = import_parse.segments_from_ja(payload.text or "")
    if not segs:
        raise HTTPException(400, "붙여넣은 내용에서 구간을 찾지 못했습니다. '시작초 | 종료초 | 일본어' 형식인지 확인하세요.")
    job_id = uuid.uuid4().hex[:12]
    duration = max((s.end for s in segs), default=0.0)
    job = Job(id=job_id, status="stage2_ready", engine="imported_ja", segments=segs,
              message=f"일본어 대본 가져오기 완료 · 구간 {len(segs)}개",
              meta=VideoMeta(source="import_ja", title=payload.title or "일본어 대본", duration=duration))
    store.save(job)
    return {"id": job_id, "status": "stage2_ready", "count": len(segs)}


# --------------------------------------------------------------------------- #
# Segment editing + reads + downloads
# --------------------------------------------------------------------------- #
@app.patch("/api/jobs/{job_id}/segments")
async def update_segments(job_id: str, payload: SegmentsUpdate):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    by_index = {s.index: s for s in job.segments}
    for patch in payload.segments:
        seg = by_index.get(patch.index)
        if seg is None:
            continue
        if patch.text_kr is not None:
            seg.text_kr = patch.text_kr
        if patch.text_ja is not None:
            seg.text_ja = patch.text_ja
        if patch.type is not None:
            seg.type = patch.type
    store.save(job)
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/jobs")
async def list_jobs():
    return [{"id": j.id, "status": j.status, "title": j.meta.title, "message": j.message}
            for j in store.list_jobs()]


@app.get("/api/voices")
async def get_voices():
    try:
        return {"voices": tts.list_voices(), "default": config.ELEVEN_VOICE_ID}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"ElevenLabs 음성 목록을 불러오지 못했습니다: {e}")


@app.get("/api/jobs/{job_id}/audio/{index}")
async def get_segment_audio(job_id: str, index: int):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    seg = next((s for s in job.segments if s.index == index), None)
    if seg is None or not seg.audio_file:
        raise HTTPException(404, "audio not found")
    path = config.job_dir(job_id) / "audio" / seg.audio_file
    if not path.exists():
        raise HTTPException(404, "audio file missing")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/jobs/{job_id}/download/{kind}")
async def download_output(job_id: str, kind: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    out_dir = config.job_dir(job_id) / "outputs"
    base = _safe_name(job.meta.title) or job_id
    mapping = {
        "mp3": ("combined.mp3", "audio/mpeg", f"{base}.mp3"),
        "wav": ("combined.wav", "audio/wav", f"{base}.wav"),
        "zip": (f"{job_id}_dub.zip", "application/zip", f"{base}_dub.zip"),
        "srt_ja": ("subtitle_ja.srt", "text/plain; charset=utf-8", f"{base}_ja.srt"),
        "srt_kr": ("subtitle_kr.srt", "text/plain; charset=utf-8", f"{base}_kr.srt"),
    }
    if kind not in mapping:
        raise HTTPException(400, "kind must be mp3|wav|zip|srt_ja|srt_kr")
    fname, media, dl = mapping[kind]
    path = out_dir / fname
    if not path.exists():
        raise HTTPException(404, "아직 생성되지 않았습니다.")
    return FileResponse(path, media_type=media, filename=dl)


@app.get("/api/health")
async def health():
    return {
        "ffmpeg": bool(config.FFMPEG_CMD),
        "anthropic_key": bool(config.ANTHROPIC_API_KEY),
        "elevenlabs_key": bool(config.ELEVENLABS_API_KEY),
    }


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #
@app.get("/")
async def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="static")
