"""APScheduler jobs for the finder: reference-channel auto-scan + morning collect.

Runs in-process (BackgroundScheduler). All failures are swallowed so a scheduler
problem never affects the dubbing pipeline or the web server. Jobs re-read
settings each run, and reschedule() re-applies interval/hour changes made in the
UI without a restart.
"""
from __future__ import annotations

import threading

from . import channels, report, settings, telegram

_scheduler = None
_lock = threading.Lock()

JOB_SCAN = "finder_ref_scan"
JOB_MORNING = "finder_morning"


# --------------------------------------------------------------------------- #
# Job bodies
# --------------------------------------------------------------------------- #
def _run_reference_scan() -> None:
    try:
        result = channels.scan_reference()
        if result.get("new_videos", 0) > 0:
            telegram.send(
                f"[소재 찾기] 레퍼런스 채널 스캔: 신규 {result['new_videos']}편 "
                f"({result['channels_scanned']}개 채널)")
    except Exception:
        pass


def _run_morning_collect() -> None:
    try:
        if not settings.get("morning_enabled"):
            return
        from . import db, search
        from .models import SearchRequest
        db.init_db()
        with db.get_conn() as c:
            cats = [r["name"] for r in c.execute("SELECT name FROM categories").fetchall()]
        req = SearchRequest(categories=cats, period="3d", order="viewCount",
                            translate_titles=True)
        run_id = search.new_run()
        search.run_search(req, run_id)          # 동기 실행(이미 백그라운드 스레드)
        rep = report.today()
        telegram.send("[소재 찾기] 아침 자동수집 완료 — " + report.summary_line(rep))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def start() -> None:
    global _scheduler
    with _lock:
        if _scheduler is not None:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except Exception:
            return
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.start()
        _apply_jobs()


def shutdown() -> None:
    global _scheduler
    with _lock:
        if _scheduler is not None:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
            _scheduler = None


def reschedule() -> None:
    """Re-apply jobs after settings change (scan_hours / morning_hour / enabled)."""
    with _lock:
        if _scheduler is not None:
            _apply_jobs()


def _apply_jobs() -> None:
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    scan_hours = max(1, int(settings.get("scan_hours") or 6))
    morning_hour = int(settings.get("morning_hour") or 7)

    _scheduler.add_job(_run_reference_scan, IntervalTrigger(hours=scan_hours),
                       id=JOB_SCAN, replace_existing=True, max_instances=1)
    _scheduler.add_job(_run_morning_collect, CronTrigger(hour=morning_hour, minute=0),
                       id=JOB_MORNING, replace_existing=True, max_instances=1)


def status() -> dict:
    with _lock:
        running = _scheduler is not None
        jobs = []
        if running:
            for j in _scheduler.get_jobs():
                jobs.append({"id": j.id,
                             "next_run": j.next_run_time.isoformat() if j.next_run_time else None})
    return {
        "running": running,
        "scan_hours": settings.get("scan_hours"),
        "morning_hour": settings.get("morning_hour"),
        "morning_enabled": bool(settings.get("morning_enabled")),
        "jobs": jobs,
    }
