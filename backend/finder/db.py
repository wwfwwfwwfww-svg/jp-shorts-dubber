"""SQLite storage for the 소재 찾기 tab (data/finder.db).

Single-user local tool: a fresh connection per operation is more than fast enough
and avoids cross-thread sharing headaches (FastAPI background tasks run in a
threadpool). WAL mode keeps concurrent reads/writes safe. Schema is created (and
category/keyword defaults seeded) idempotently on startup via init_db().
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterable, Optional

from .. import config

_init_lock = threading.Lock()
_initialized = False

# Default categories + their seed keywords (1-8 in the spec).
DEFAULT_CATEGORIES = [
    ("동물", None, ["funny dog", "funny cat", "cute animals", "animal reaction"]),
    ("아이디어/DIY", None, ["genius idea", "life hack", "clever invention", "satisfying tool"]),
    ("반전/리액션", None, ["unexpected ending", "plot twist", "reaction", "wait for it"]),
    ("실패/웃긴 순간", None, ["fail", "funny moments", "oops"]),
    ("묘기/스포츠", None, ["amazing skill", "satisfying", "talent"]),
    ("예능 클립", "방송 원본 포함 – 클레임 주의", []),
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(config.FINDER_DB))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        config.DATA_DIR.mkdir(exist_ok=True)
        with get_conn() as c:
            c.executescript(_SCHEMA)
            _seed(c)
        _initialized = True


_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id       TEXT PRIMARY KEY,
    title          TEXT DEFAULT '',
    title_ko       TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    channel_id     TEXT DEFAULT '',
    channel_title  TEXT DEFAULT '',
    published_at   TEXT DEFAULT '',
    duration_sec   INTEGER DEFAULT 0,
    views          INTEGER DEFAULT 0,
    likes          INTEGER DEFAULT 0,
    subscribers    INTEGER DEFAULT 0,
    sub_multiple   REAL DEFAULT 0,
    chan_avg_multiple REAL DEFAULT 0,
    daily_views    REAL DEFAULT 0,
    like_rate      REAL DEFAULT 0,
    region         TEXT DEFAULT '',
    lang           TEXT DEFAULT '',
    category       TEXT DEFAULT '',
    category_ai    INTEGER DEFAULT 0,
    japan_unentered INTEGER,              -- NULL = 미판별
    prev_views     INTEGER,
    prev_views_at  TEXT,
    first_seen     TEXT DEFAULT '',
    collected_at   TEXT DEFAULT '',
    status         TEXT DEFAULT 'new',    -- new|bookmark|working|done|excluded
    watched        INTEGER DEFAULT 0,
    thumbnail      TEXT DEFAULT '',
    -- 영상 구조 통계용(수집 가능한 범위)
    has_caption    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_videos_views    ON videos(views);
CREATE INDEX IF NOT EXISTS idx_videos_category ON videos(category);
CREATE INDEX IF NOT EXISTS idx_videos_channel  ON videos(channel_id);

CREATE TABLE IF NOT EXISTS channels (
    channel_id    TEXT PRIMARY KEY,
    title         TEXT DEFAULT '',
    subscribers   INTEGER DEFAULT 0,
    avg_views     REAL DEFAULT 0,
    uploads_playlist TEXT DEFAULT '',
    avg_cached_at TEXT,
    is_reference  INTEGER DEFAULT 0,
    ref_category  TEXT DEFAULT '',
    last_scan_at  TEXT,
    added_at      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS keywords (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT DEFAULT '',
    text     TEXT NOT NULL,
    enabled  INTEGER DEFAULT 1,
    UNIQUE(category, text)
);

CREATE TABLE IF NOT EXISTS categories (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT UNIQUE NOT NULL,
    warn_tag TEXT
);

CREATE TABLE IF NOT EXISTS japan_check (
    video_id   TEXT PRIMARY KEY,
    unentered  INTEGER,
    jp_keywords TEXT DEFAULT '',
    checked_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quota_log (
    date        TEXT PRIMARY KEY,
    points_used INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _seed(c: sqlite3.Connection) -> None:
    have_cat = c.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if have_cat == 0:
        for name, warn, kws in DEFAULT_CATEGORIES:
            c.execute("INSERT OR IGNORE INTO categories(name, warn_tag) VALUES(?,?)",
                      (name, warn))
            for kw in kws:
                c.execute("INSERT OR IGNORE INTO keywords(category, text, enabled) "
                          "VALUES(?,?,1)", (name, kw))


# --------------------------------------------------------------------------- #
# Small typed helpers
# --------------------------------------------------------------------------- #
def get_setting(key: str, default=None):
    with get_conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return row["value"]


def set_setting(key: str, value) -> None:
    with get_conn() as c:
        c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value, ensure_ascii=False)))


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list:
    return [dict(r) for r in rows]
