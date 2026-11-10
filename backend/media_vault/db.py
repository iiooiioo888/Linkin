"""SQLite 儲存層（SQL 可移植至 PostgreSQL）。"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.media_vault.config import MediaVaultConfig, load_config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS unified_posts (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    compliance_basis TEXT NOT NULL DEFAULT 'unknown',
    crawl_method TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL DEFAULT 'image',
    caption TEXT,
    summary TEXT,
    dedup_hash TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'yellow',
    created_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES unified_posts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_size INTEGER NOT NULL DEFAULT 0,
    width INTEGER,
    height INTEGER,
    mime TEXT NOT NULL DEFAULT 'application/octet-stream'
);

CREATE TABLE IF NOT EXISTS ingest_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT 'error',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_job ON unified_posts(job_id);
CREATE INDEX IF NOT EXISTS idx_posts_batch ON unified_posts(batch_id);
CREATE INDEX IF NOT EXISTS idx_posts_platform ON unified_posts(platform);
CREATE INDEX IF NOT EXISTS idx_posts_compliance ON unified_posts(compliance_basis);
CREATE INDEX IF NOT EXISTS idx_posts_risk ON unified_posts(risk_level);
CREATE INDEX IF NOT EXISTS idx_posts_dedup ON unified_posts(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_assets_post ON media_assets(post_id);
CREATE INDEX IF NOT EXISTS idx_ingest_job ON ingest_events(job_id);
CREATE INDEX IF NOT EXISTS idx_ingest_created ON ingest_events(created_at);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_cfg: MediaVaultConfig | None = None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def reset_media_vault_db() -> None:
    global _conn, _cfg
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except sqlite3.Error:
                pass
        _conn = None
        _cfg = None


def get_config() -> MediaVaultConfig:
    global _cfg
    with _lock:
        if _cfg is None:
            _cfg = load_config()
        return _cfg


def _connect(cfg: MediaVaultConfig) -> sqlite3.Connection:
    path = cfg.database_path
    if str(path) == ":memory:":
        conn = sqlite3.connect(":memory:", check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def connection() -> sqlite3.Connection:
    global _conn
    with _lock:
        cfg = get_config()
        if _conn is None:
            _conn = _connect(cfg)
        return _conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def log_ingest_event(
    *,
    job_id: str = "",
    batch_id: str = "",
    level: str = "error",
    message: str,
) -> None:
    conn = connection()
    conn.execute(
        """
        INSERT INTO ingest_events (id, job_id, batch_id, level, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (uuid.uuid4().hex, job_id, batch_id, level, message[:4000], _utc_now()),
    )
    conn.commit()


def insert_post(row: dict[str, Any]) -> str:
    post_id = row.get("id") or uuid.uuid4().hex
    conn = connection()
    conn.execute(
        """
        INSERT INTO unified_posts (
            id, platform, source_url, author, batch_id, job_id,
            compliance_basis, crawl_method, media_type, caption, summary,
            dedup_hash, risk_level, created_at, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            row["platform"],
            row.get("source_url") or "",
            row.get("author") or "",
            row.get("batch_id") or "",
            row.get("job_id") or "",
            row.get("compliance_basis") or "unknown",
            row.get("crawl_method") or "",
            row.get("media_type") or "image",
            row.get("caption"),
            row.get("summary"),
            row.get("dedup_hash") or "",
            row.get("risk_level") or "yellow",
            row.get("created_at") or _utc_now(),
            row.get("ingested_at") or _utc_now(),
        ),
    )
    conn.commit()
    return post_id


def insert_asset(row: dict[str, Any]) -> str:
    asset_id = row.get("id") or uuid.uuid4().hex
    conn = connection()
    conn.execute(
        """
        INSERT INTO media_assets (
            id, post_id, kind, relative_path, byte_size, width, height, mime
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            row["post_id"],
            row["kind"],
            row["relative_path"],
            int(row.get("byte_size") or 0),
            row.get("width"),
            row.get("height"),
            row.get("mime") or "application/octet-stream",
        ),
    )
    conn.commit()
    return asset_id


def find_post_by_dedup(dedup_hash: str) -> str | None:
    if not dedup_hash:
        return None
    conn = connection()
    row = conn.execute(
        "SELECT id FROM unified_posts WHERE dedup_hash = ? LIMIT 1",
        (dedup_hash,),
    ).fetchone()
    return str(row["id"]) if row else None


def relative_to_abs(cfg: MediaVaultConfig, relative_path: str) -> Path:
    rel = relative_path.lstrip("/\\")
    return (cfg.media_root / rel).resolve()


def ensure_media_dirs(cfg: MediaVaultConfig) -> None:
    cfg.originals_dir.mkdir(parents=True, exist_ok=True)
    cfg.thumbs_dir.mkdir(parents=True, exist_ok=True)
