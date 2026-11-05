"""Media Vault HTTP API。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.media_vault import db as vault_db
from backend.media_vault.config import load_config
from backend.media_vault.ingest import ingest_job_results
from backend.media_vault.monitor import monitor_summary

router = APIRouter(prefix="/media-vault", tags=["media-vault"])


class ReplayIngestBody(BaseModel):
    job_id: str = Field(min_length=1)


def _row_post(row) -> dict[str, Any]:
    return dict(row)


def _assets_for_post(post_id: str) -> list[dict[str, Any]]:
    conn = vault_db.connection()
    rows = conn.execute(
        "SELECT * FROM media_assets WHERE post_id = ? ORDER BY kind",
        (post_id,),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["url"] = f"/media-vault/files/{item['id']}"
        out.append(item)
    return out


@router.get("/images")
def list_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    platform: list[str] | None = Query(None),
    batch_id: str | None = None,
    compliance_basis: str | None = None,
    media_type: str | None = None,
    risk_level: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    conn = vault_db.connection()
    clauses: list[str] = []
    params: list[Any] = []

    if platform:
        placeholders = ",".join("?" for _ in platform)
        clauses.append(f"platform IN ({placeholders})")
        params.extend(platform)
    if batch_id:
        clauses.append("batch_id = ?")
        params.append(batch_id)
    if compliance_basis:
        clauses.append("compliance_basis = ?")
        params.append(compliance_basis)
    if media_type:
        clauses.append("media_type = ?")
        params.append(media_type)
    if risk_level:
        clauses.append("risk_level = ?")
        params.append(risk_level)
    if q:
        clauses.append("(author LIKE ? OR source_url LIKE ? OR caption LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) AS c FROM unified_posts {where}", params).fetchone()["c"]
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT * FROM unified_posts {where}
        ORDER BY ingested_at DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()

    items = []
    for row in rows:
        post = _row_post(row)
        assets = _assets_for_post(post["id"])
        thumb = next((a for a in assets if a["kind"] == "thumb_300"), assets[0] if assets else None)
        post["thumb_url"] = thumb["url"] if thumb else None
        items.append(post)

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "items": items,
    }


@router.get("/images/{post_id}")
def get_image_detail(post_id: str) -> dict[str, Any]:
    conn = vault_db.connection()
    row = conn.execute("SELECT * FROM unified_posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="貼文不存在")
    post = _row_post(row)
    post["assets"] = _assets_for_post(post_id)
    return post


@router.get("/files/{asset_id}")
def serve_asset(asset_id: str) -> FileResponse:
    conn = vault_db.connection()
    row = conn.execute("SELECT * FROM media_assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="資產不存在")
    cfg = load_config()
    path = vault_db.relative_to_abs(cfg, row["relative_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="檔案不存在")
    return FileResponse(path, media_type=row["mime"] or None, filename=path.name)


@router.get("/monitor/summary")
def get_monitor_summary() -> dict[str, Any]:
    return monitor_summary()


@router.post("/ingest/replay")
def replay_ingest(body: ReplayIngestBody) -> dict[str, Any]:
    from backend.mediacrawler.jobs import get_job_manager

    job = get_job_manager().get_job(body.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    req = job.request if isinstance(job.request, dict) else {}
    stats = ingest_job_results(
        job.job_id,
        Path(job.results_dir),
        platform=str(req.get("platform") or ""),
        batch_id=job.job_id,
        crawl_method=str(req.get("crawl_type") or ""),
        compliance_basis="public",
    )
    return {"job_id": job.job_id, **stats}


def register_media_vault(app) -> None:
    app.include_router(router)
