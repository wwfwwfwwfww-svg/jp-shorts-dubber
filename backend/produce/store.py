"""Disk-backed store for 제작 jobs (data/produce/<id>/job.json). Isolated from the
dubbing job store (backend/store.py) — separate directory, separate cache."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional

from .. import config
from .models import ProduceJob

PRODUCE_DIR = config.DATA_DIR / "produce"

_lock = threading.Lock()
_cache: Dict[str, ProduceJob] = {}


def job_dir(job_id: str) -> Path:
    d = PRODUCE_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def save(job: ProduceJob) -> None:
    with _lock:
        _cache[job.id] = job
        _path(job.id).write_text(job.model_dump_json(indent=2), encoding="utf-8")


def get(job_id: str) -> Optional[ProduceJob]:
    with _lock:
        if job_id in _cache:
            return _cache[job_id]
    p = PRODUCE_DIR / job_id / "job.json"
    if p.exists():
        job = ProduceJob.model_validate_json(p.read_text(encoding="utf-8"))
        with _lock:
            _cache[job_id] = job
        return job
    return None


def list_jobs() -> List[ProduceJob]:
    out: List[ProduceJob] = []
    if not PRODUCE_DIR.exists():
        return out
    for d in sorted(PRODUCE_DIR.glob("*/job.json")):
        try:
            out.append(ProduceJob.model_validate_json(d.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
