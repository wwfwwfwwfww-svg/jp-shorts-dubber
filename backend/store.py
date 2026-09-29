"""Simple disk-backed job store (single-user local tool).

Each job is persisted as data/<job_id>/job.json. An in-memory cache keeps the
latest state for quick access; the JSON file is the source of truth on restart.
"""
from __future__ import annotations

import json
import threading
from typing import Dict, List, Optional

from . import config
from .models import Job

_lock = threading.Lock()
_cache: Dict[str, Job] = {}


def _job_json_path(job_id: str):
    return config.job_dir(job_id) / "job.json"


def save(job: Job) -> None:
    with _lock:
        _cache[job.id] = job
        path = _job_json_path(job.id)
        path.write_text(job.model_dump_json(indent=2), encoding="utf-8")


def get(job_id: str) -> Optional[Job]:
    with _lock:
        if job_id in _cache:
            return _cache[job_id]
    path = config.DATA_DIR / job_id / "job.json"
    if path.exists():
        job = Job.model_validate_json(path.read_text(encoding="utf-8"))
        with _lock:
            _cache[job_id] = job
        return job
    return None


def list_jobs() -> List[Job]:
    jobs: List[Job] = []
    for d in sorted(config.DATA_DIR.glob("*/job.json")):
        try:
            jobs.append(Job.model_validate_json(d.read_text(encoding="utf-8")))
        except Exception:
            continue
    return jobs
