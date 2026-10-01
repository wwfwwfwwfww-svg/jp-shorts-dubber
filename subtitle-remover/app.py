"""자막 지우개 — 별도 로컬 웹앱 (기존 더빙/소재찾기 앱과 완전 분리).

영상 업로드 → 지울 영역 박스 지정 → 그 영역을 영상 전체에서 지우기 → 다운로드.
포트 8008. torch/GPU 불필요(cv2 인페인팅). 실행: 자막지우개_실행.bat
"""
from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import List

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import inpaint

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
WORK.mkdir(exist_ok=True)
STATIC = ROOT / "static"

app = FastAPI(title="자막 지우개")

_jobs: dict = {}
_lock = threading.Lock()


class Box(BaseModel):
    x: float
    y: float
    w: float
    h: float


class ProcessReq(BaseModel):
    boxes: List[Box]
    radius: int = 6


def _set(jid: str, **kw) -> None:
    with _lock:
        _jobs.setdefault(jid, {}).update(kw)


def _get(jid: str) -> dict:
    with _lock:
        return dict(_jobs.get(jid, {}))


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    jid = uuid.uuid4().hex[:12]
    d = WORK / jid
    d.mkdir(parents=True, exist_ok=True)
    src = d / "source.mp4"
    with src.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        w, h = inpaint.first_frame(str(src), str(d / "frame.jpg"))
    except Exception as e:
        raise HTTPException(400, f"영상을 읽지 못했습니다: {e}")
    _set(jid, status="uploaded", width=w, height=h)
    return {"id": jid, "width": w, "height": h}


@app.get("/api/{jid}/frame")
def frame(jid: str):
    p = WORK / jid / "frame.jpg"
    if not p.exists():
        raise HTTPException(404, "프레임 없음")
    return FileResponse(p, media_type="image/jpeg")


@app.post("/api/{jid}/process")
def process(jid: str, req: ProcessReq, bg: BackgroundTasks):
    if not _get(jid):
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    if not req.boxes:
        raise HTTPException(400, "지울 영역(박스)을 하나 이상 지정하세요.")
    _set(jid, status="processing", message="시작...")
    boxes = [b.model_dump() for b in req.boxes]
    bg.add_task(_run, jid, boxes, req.radius)
    return {"ok": True}


def _run(jid: str, boxes: list, radius: int) -> None:
    d = WORK / jid
    try:
        inpaint.process(str(d / "source.mp4"), str(d / "output.mp4"), boxes, radius,
                        progress=lambda m: _set(jid, message=m))
        _set(jid, status="done", message="완료 — 결과를 확인하세요.")
    except Exception as e:
        _set(jid, status="error", message=f"오류: {e}")


@app.get("/api/{jid}")
def status(jid: str):
    j = _get(jid)
    if not j:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return {"status": j.get("status"), "message": j.get("message", ""),
            "width": j.get("width"), "height": j.get("height")}


@app.get("/api/{jid}/result")
def result(jid: str):
    p = WORK / jid / "output.mp4"
    if not p.exists():
        raise HTTPException(404, "결과가 아직 없습니다.")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/{jid}/download")
def download(jid: str):
    p = WORK / jid / "output.mp4"
    if not p.exists():
        raise HTTPException(404, "결과가 아직 없습니다.")
    return FileResponse(p, media_type="video/mp4", filename=f"{jid}_clean.mp4")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")
