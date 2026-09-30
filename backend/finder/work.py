"""「작업하기」 — 소재 영상을 작업 폴더에 다운로드하고 2단계(제작)로 넘길 준비.

기존 더빙 파이프라인의 yt-dlp 다운로더(pipeline/download.py)를 재사용한다. 실제 제작
파이프라인 호출은 2단계에서 구현하며, 지금은 **핸드오프 페이로드**만 만든다.
"""
from __future__ import annotations

from .. import config
from ..pipeline import download
from . import db, query

COPYRIGHT_NOTICE = (
    "받은 영상은 분석·학습용입니다. 그대로 올리거나 잘라서 사용하면 저작권 문제가 생길 수 있습니다."
)

WORK_DIR = config.DATA_DIR / "finder_work"


def _set_status(video_id: str, status: str) -> None:
    with db.get_conn() as c:
        c.execute("UPDATE videos SET status=? WHERE video_id=?", (status, video_id))


def handoff_payload(video: dict, file_path: str = "") -> dict:
    """2단계 제작 화면으로 넘길 최소 정보(연결 지점). 실제 제작은 2단계에서 처리."""
    return {
        "source": "finder",
        "video_id": video["video_id"],
        "url": f"https://youtu.be/{video['video_id']}",
        "title": video.get("title", ""),
        "title_ko": video.get("title_ko", ""),
        "region": video.get("region", ""),
        "category": video.get("category", ""),
        "file": file_path,
    }


def download_video(video_id: str) -> dict:
    """Background: download the source mp4 into the work folder, mark 'working'."""
    video = query.get_video(video_id)
    if not video:
        return {"ok": False, "error": "영상을 찾을 수 없습니다."}
    dest = WORK_DIR / video_id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        # 소리가 항상 포함되도록 영상+오디오 병합 포맷을 강제(무음 다운로드 방지).
        path, _title = download.download_url(
            f"https://youtu.be/{video_id}", dest, fmt="bestvideo+bestaudio/best")
    except Exception as e:
        return {"ok": False, "error": f"다운로드 실패: {e}"}
    return {"ok": True, "file": str(path), "handoff": handoff_payload(video, str(path))}


def start(video_id: str) -> dict:
    """Called synchronously by the route: mark working + return the notice/handoff.
    The actual download runs as a background task."""
    video = query.get_video(video_id)
    if not video:
        return {"ok": False, "error": "영상을 찾을 수 없습니다."}
    _set_status(video_id, "working")
    return {
        "ok": True,
        "message": COPYRIGHT_NOTICE + " 작업 폴더로 다운로드를 시작합니다.",
        "notice": COPYRIGHT_NOTICE,
        "handoff": handoff_payload(video),
        "stage2": "connected",   # 2단계 연결 지점(제작 파이프라인은 다음 요청에서 구현)
    }
