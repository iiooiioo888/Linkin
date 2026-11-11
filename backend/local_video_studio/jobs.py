"""M2 GenerationJob／Asset／Resource 業務邏輯。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.local_video_studio.models import Asset, GenerationJob, Project, ResourceRecord, Shot
from backend.local_video_studio.schemas import (
    AssetOut,
    JobComplete,
    JobCreate,
    JobOut,
)


def _now() -> datetime:
    return datetime.now(UTC)


def asset_to_out(asset: Asset | None) -> AssetOut | None:
    if asset is None:
        return None
    return AssetOut(
        id=asset.id,
        project_id=asset.project_id,
        shot_id=asset.shot_id,
        type=asset.type,
        relative_path=asset.relative_path,
        mime=asset.mime,
        bytes=asset.bytes,
        sha256=asset.sha256,
        created_at=asset.created_at,
    )


def job_to_out(session: Session, job: GenerationJob) -> JobOut:
    asset = None
    if job.status == "succeeded":
        asset = session.scalar(
            select(Asset)
            .where(Asset.project_id == job.project_id, Asset.shot_id == job.shot_id)
            .order_by(Asset.created_at.desc())
        )
    from backend.local_video_studio.job_log import log_relative_path

    log_rel = job.log_relative_path or log_relative_path(job.project_id, job.id)
    return JobOut(
        id=job.id,
        project_id=job.project_id,
        shot_id=job.shot_id,
        job_type=job.job_type,
        workflow_template=job.workflow_template,
        workflow_version=job.workflow_version,
        params_json=job.params_json,
        status=job.status,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        priority=job.priority,
        data_class=job.data_class,
        assigned_agent=job.assigned_agent,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        error_summary=job.error,
        log_relative_path=log_rel,
        created_at=job.created_at,
        asset=asset_to_out(asset) if job.status == "succeeded" else None,
    )


def create_job(session: Session, body: JobCreate) -> JobOut:
    if session.get(Project, body.project_id) is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    shot = session.get(Shot, body.shot_id)
    if shot is None or shot.project_id != body.project_id:
        raise HTTPException(status_code=404, detail="鏡頭不存在或不屬於此專案")
    if body.data_class != "local_only":
        # M2：雲端關閉，僅允許 local_only
        from backend.local_video_studio.config import load_config

        if not load_config().cloud_enabled and body.data_class != "local_only":
            raise HTTPException(status_code=400, detail="CLOUD_ENABLED=false，僅允許 local_only")

    params = dict(body.params or {})
    if body.required_models:
        params["required_models"] = list(body.required_models)

    from backend.local_video_studio.job_log import log_relative_path

    job = GenerationJob(
        project_id=body.project_id,
        shot_id=body.shot_id,
        job_type=body.job_type,
        workflow_template=body.workflow_template,
        workflow_version=body.workflow_version,
        params_json=params,
        priority=body.priority,
        data_class=body.data_class,
        max_attempts=body.max_attempts,
        status="queued",
        attempt=0,
    )
    session.add(job)
    session.flush()
    job.log_relative_path = log_relative_path(job.project_id, job.id)
    session.flush()
    return job_to_out(session, job)


def list_jobs(
    session: Session,
    *,
    status: str | None = None,
    assigned_agent: str | None = None,
    project_id: str | None = None,
    unassigned: bool = False,
) -> list[JobOut]:
    stmt = select(GenerationJob).order_by(
        GenerationJob.priority.asc(), GenerationJob.created_at.asc()
    )
    if status:
        stmt = stmt.where(GenerationJob.status == status)
    if project_id:
        stmt = stmt.where(GenerationJob.project_id == project_id)
    if unassigned:
        stmt = stmt.where(GenerationJob.assigned_agent.is_(None))
    elif assigned_agent is not None:
        stmt = stmt.where(GenerationJob.assigned_agent == assigned_agent)
    rows = session.scalars(stmt).all()
    return [job_to_out(session, j) for j in rows]


def get_job(session: Session, job_id: str) -> JobOut:
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return job_to_out(session, job)


def claim_job(session: Session, job_id: str, agent_id: str) -> JobOut:
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    if job.status != "queued":
        raise HTTPException(status_code=409, detail=f"任務狀態不可 claim：{job.status}")
    if job.assigned_agent and job.assigned_agent != agent_id:
        raise HTTPException(status_code=409, detail="任務已被其他 agent 認領")
    job.assigned_agent = agent_id
    job.status = "running"
    job.attempt = int(job.attempt or 0) + 1
    job.started_at = _now()
    job.error = None
    session.flush()
    return job_to_out(session, job)


def complete_job(session: Session, job_id: str, body: JobComplete) -> JobOut:
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    if job.status not in {"running", "queued"}:
        raise HTTPException(status_code=409, detail=f"任務狀態不可 complete：{job.status}")

    job.finished_at = _now()
    if body.status == "succeeded":
        job.status = "succeeded"
        job.error = None
        if body.asset is None:
            raise HTTPException(status_code=422, detail="succeeded 須附帶 asset")
        asset = Asset(
            project_id=job.project_id,
            shot_id=job.shot_id,
            type=body.asset.type,
            relative_path=body.asset.relative_path,
            mime=body.asset.mime,
            bytes=body.asset.bytes,
            sha256=body.asset.sha256,
        )
        session.add(asset)
        session.flush()
        shot = session.get(Shot, job.shot_id)
        if shot is not None:
            if job.job_type == "keyframe":
                shot.selected_keyframe_asset_id = asset.id
                shot.status = "keyframe_ready"
            elif job.job_type == "draft":
                shot.selected_clip_asset_id = asset.id
                shot.status = "draft_ready"
            elif job.job_type == "refine":
                shot.selected_clip_asset_id = asset.id
                shot.status = "refine_ready"
    else:
        job.status = "failed"
        job.error = body.error or "failed"

    if body.resource is not None:
        session.add(
            ResourceRecord(
                job_id=job.id,
                gpu_minutes=body.resource.gpu_minutes,
                wall_minutes=body.resource.wall_minutes,
                attempts=body.resource.attempts if body.resource.attempts is not None else job.attempt,
                discarded_count=body.resource.discarded_count,
                storage_bytes=body.resource.storage_bytes,
                api_calls=body.resource.api_calls,
                electricity_note=body.resource.electricity_note,
            )
        )
    session.flush()
    return job_to_out(session, job)


def cancel_job(session: Session, job_id: str) -> JobOut:
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    if job.status in {"succeeded", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"任務狀態不可 cancel：{job.status}")
    job.status = "cancelled"
    job.finished_at = _now()
    session.flush()
    return job_to_out(session, job)


def retry_job(session: Session, job_id: str) -> JobOut:
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    if job.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"任務狀態不可 retry：{job.status}")
    if int(job.attempt or 0) >= int(job.max_attempts or 0):
        raise HTTPException(status_code=409, detail="已達 max_attempts")
    job.status = "queued"
    job.assigned_agent = None
    job.started_at = None
    job.finished_at = None
    job.error = None
    session.flush()
    return job_to_out(session, job)


def list_assets(
    session: Session, project_id: str, *, asset_type: str | None = None
) -> list[AssetOut]:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    stmt = select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at.desc())
    if asset_type:
        stmt = stmt.where(Asset.type == asset_type)
    return [asset_to_out(a) for a in session.scalars(stmt).all() if a]  # type: ignore[misc]


def resource_summary(session: Session, project_id: str):
    from backend.local_video_studio.schemas import ResourceSummary

    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    from backend.local_video_studio.models import ResourceRecord

    jobs = session.scalars(
        select(GenerationJob).where(GenerationJob.project_id == project_id)
    ).all()
    assets = session.scalars(select(Asset).where(Asset.project_id == project_id)).all()
    gpu = wall = discarded = api_calls = attempts = storage = 0.0
    for job in jobs:
        attempts += int(job.attempt or 0)
        recs = session.scalars(
            select(ResourceRecord).where(ResourceRecord.job_id == job.id)
        ).all()
        for rec in recs:
            gpu += float(rec.gpu_minutes or 0)
            wall += float(rec.wall_minutes or 0)
            discarded += int(rec.discarded_count or 0)
            api_calls += int(rec.api_calls or 0)
            storage += float(rec.storage_bytes or 0)
    for asset in assets:
        storage += float(asset.bytes or 0)
    return ResourceSummary(
        project_id=project_id,
        gpu_minutes=round(gpu, 4),
        wall_minutes=round(wall, 4),
        attempts=int(attempts),
        discarded_count=int(discarded),
        storage_bytes=int(storage),
        api_calls=int(api_calls),
        job_count=len(jobs),
        asset_count=len(assets),
    )
