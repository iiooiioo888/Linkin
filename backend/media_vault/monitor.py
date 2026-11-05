"""監控摘要查詢（SQLite；Postgres 等價見 docs SQL）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.media_vault.config import load_config
from backend.media_vault import db as vault_db


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def monitor_summary() -> dict[str, Any]:
    conn = vault_db.connection()
    cfg = load_config()
    now = _utc_now()
    today_iso = _day_start(now).isoformat()
    since_24h = (now - timedelta(hours=24)).isoformat()

    today_posts = conn.execute(
        "SELECT COUNT(*) AS c FROM unified_posts WHERE ingested_at >= ?",
        (today_iso,),
    ).fetchone()["c"]

    total_posts = conn.execute("SELECT COUNT(*) AS c FROM unified_posts").fetchone()["c"]

    compliance_rows = conn.execute(
        """
        SELECT compliance_basis AS label, COUNT(*) AS count
        FROM unified_posts
        GROUP BY compliance_basis
        ORDER BY count DESC
        """
    ).fetchall()

    storage_rows = conn.execute(
        """
        SELECT p.platform AS platform, COALESCE(SUM(a.byte_size), 0) AS bytes
        FROM unified_posts p
        LEFT JOIN media_assets a ON a.post_id = p.id
        GROUP BY p.platform
        ORDER BY bytes DESC
        """
    ).fetchall()

    ingest_series = _ingest_buckets(conn, since_24h)

    ingest_errors = conn.execute(
        """
        SELECT id, job_id, batch_id, level, message, created_at
        FROM ingest_events
        ORDER BY created_at DESC
        LIMIT 20
        """
    ).fetchall()

    mc_failures = _mediacrawler_failures(limit=20)

    dedup_skipped = conn.execute(
        """
        SELECT COUNT(DISTINCT dedup_hash) AS distinct_h,
               COUNT(*) AS total
        FROM unified_posts
        WHERE dedup_hash != ''
        """
    ).fetchone()
    distinct_h = int(dedup_skipped["distinct_h"] or 0)
    total_with_hash = int(dedup_skipped["total"] or 0)
    dedup_rate = round(1 - distinct_h / total_with_hash, 4) if total_with_hash else 0.0

    success_rate = _job_success_rate()

    return {
        "today_ingested": int(today_posts),
        "total_posts": int(total_posts),
        "success_rate": success_rate,
        "dedup_collision_rate": dedup_rate,
        "ingest_series_24h": ingest_series,
        "compliance_distribution": [dict(r) for r in compliance_rows],
        "storage_by_platform": [dict(r) for r in storage_rows],
        "ingest_errors": [dict(r) for r in ingest_errors],
        "mediacrawler_failures": mc_failures,
        "media_root": str(cfg.media_root),
    }


def _ingest_buckets(conn, since_iso: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ingested_at FROM unified_posts WHERE ingested_at >= ?
        """,
        (since_iso,),
    ).fetchall()
    buckets: dict[str, int] = {}
    for row in rows:
        ts = row["ingested_at"]
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    return [{"bucket": k, "count": v} for k, v in sorted(buckets.items())]


def _job_success_rate() -> float | None:
    try:
        from backend.mediacrawler.jobs import get_job_manager

        jobs = get_job_manager().list_jobs(limit=200)
    except Exception:
        return None
    if not jobs:
        return None
    terminal = [j for j in jobs if j.get("status") in {"completed", "failed"}]
    if not terminal:
        return None
    ok = sum(1 for j in terminal if j.get("status") == "completed")
    return round(ok / len(terminal), 4)


def _mediacrawler_failures(limit: int) -> list[dict[str, Any]]:
    try:
        from backend.mediacrawler.jobs import get_job_manager

        jobs = get_job_manager().list_jobs(limit=limit)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for job in jobs:
        if job.get("status") != "failed":
            continue
        req = job.get("request") if isinstance(job.get("request"), dict) else {}
        out.append(
            {
                "job_id": job.get("job_id"),
                "error": job.get("error") or "",
                "platform": req.get("platform") or "",
                "finished_at": job.get("finished_at"),
            }
        )
    return out
