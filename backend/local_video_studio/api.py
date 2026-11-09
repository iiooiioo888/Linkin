"""Local Video Studio HTTP API（M0 health + M1 CRUD + M2 jobs）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy.orm import Session

from backend.local_video_studio import compose_service
from backend.local_video_studio import jobs as jobs_service
from backend.local_video_studio import reviews as reviews_service
from backend.local_video_studio import service
from backend.local_video_studio.config import load_config
from backend.local_video_studio.db import get_session_factory, init_db
from backend.local_video_studio.schemas import (
    AssetOut,
    ComplianceOut,
    ComposeOut,
    ComposeRequest,
    JobComplete,
    JobCreate,
    JobOut,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    ResourceSummary,
    ReviewCreate,
    ReviewOut,
    ReviewQueueItem,
    ScriptOut,
    ScriptUpload,
    ShotCreate,
    ShotOut,
    ShotPatch,
)

router = APIRouter(prefix="/local-video-studio", tags=["local-video-studio"])
v1 = APIRouter(prefix="/api/v1", tags=["local-video-studio-v1"])


def _require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    cfg = load_config()
    expected = (cfg.api_key or "").strip()
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="無效的 API Key")


def get_db() -> Any:
    init_db()
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/health")
def health() -> dict[str, Any]:
    """模組探針：``{ok: true}``。不呼叫雲端或 ComfyUI。"""
    cfg = load_config()
    return {
        "ok": True,
        "module": "local-video-studio",
        "milestone": "M6",
        "cloud_enabled": cfg.cloud_enabled,
        "use_mock_comfy": cfg.use_mock_comfy,
        "app_env": cfg.app_env,
    }


@v1.get("/health")
def health_v1() -> dict[str, Any]:
    return health()


@v1.post("/projects", response_model=ProjectOut, dependencies=[Depends(_require_api_key)])
def api_create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    return service.create_project(db, body)


@v1.get("/projects", response_model=list[ProjectOut], dependencies=[Depends(_require_api_key)])
def api_list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    return service.list_projects(db)


@v1.get("/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(_require_api_key)])
def api_get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    return service.get_project(db, project_id)


@v1.patch("/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(_require_api_key)])
def api_patch_project(
    project_id: str, body: ProjectPatch, db: Session = Depends(get_db)
) -> ProjectOut:
    return service.patch_project(db, project_id, body)


@v1.post(
    "/projects/{project_id}/scripts",
    response_model=ScriptOut,
    dependencies=[Depends(_require_api_key)],
)
def api_upload_script(
    project_id: str, body: ScriptUpload, db: Session = Depends(get_db)
) -> ScriptOut:
    return service.upload_script(db, project_id, body)


@v1.post(
    "/projects/{project_id}/shots",
    response_model=ShotOut,
    dependencies=[Depends(_require_api_key)],
)
def api_create_shot(
    project_id: str, body: ShotCreate, db: Session = Depends(get_db)
) -> ShotOut:
    return service.create_shot(db, project_id, body)


@v1.get(
    "/projects/{project_id}/shots",
    response_model=list[ShotOut],
    dependencies=[Depends(_require_api_key)],
)
def api_list_shots(project_id: str, db: Session = Depends(get_db)) -> list[ShotOut]:
    return service.list_shots(db, project_id)


@v1.patch("/shots/{shot_id}", response_model=ShotOut, dependencies=[Depends(_require_api_key)])
def api_patch_shot(shot_id: str, body: ShotPatch, db: Session = Depends(get_db)) -> ShotOut:
    return service.patch_shot(db, shot_id, body)


@v1.post("/jobs", response_model=JobOut, dependencies=[Depends(_require_api_key)])
def api_create_job(body: JobCreate, db: Session = Depends(get_db)) -> JobOut:
    return jobs_service.create_job(db, body)


@v1.get("/jobs", response_model=list[JobOut], dependencies=[Depends(_require_api_key)])
def api_list_jobs(
    status: str | None = None,
    assigned_agent: str | None = Query(default=None),
    project_id: str | None = None,
    unassigned: bool = False,
    db: Session = Depends(get_db),
) -> list[JobOut]:
    # 規格：GET /jobs?status=queued&assigned_agent=...；未帶 agent 時可拉 unassigned
    if status == "queued" and assigned_agent is None:
        unassigned = True
    return jobs_service.list_jobs(
        db,
        status=status,
        assigned_agent=assigned_agent,
        project_id=project_id,
        unassigned=unassigned,
    )


@v1.get("/jobs/{job_id}", response_model=JobOut, dependencies=[Depends(_require_api_key)])
def api_get_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    return jobs_service.get_job(db, job_id)


@v1.post("/jobs/{job_id}/claim", response_model=JobOut, dependencies=[Depends(_require_api_key)])
def api_claim_job(
    job_id: str,
    agent_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JobOut:
    cfg = load_config()
    return jobs_service.claim_job(db, job_id, agent_id or cfg.agent_id)


@v1.post("/jobs/{job_id}/complete", response_model=JobOut, dependencies=[Depends(_require_api_key)])
def api_complete_job(
    job_id: str, body: JobComplete, db: Session = Depends(get_db)
) -> JobOut:
    return jobs_service.complete_job(db, job_id, body)


@v1.post("/jobs/{job_id}/cancel", response_model=JobOut, dependencies=[Depends(_require_api_key)])
def api_cancel_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    return jobs_service.cancel_job(db, job_id)


@v1.post("/jobs/{job_id}/retry", response_model=JobOut, dependencies=[Depends(_require_api_key)])
def api_retry_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    return jobs_service.retry_job(db, job_id)


@v1.get(
    "/projects/{project_id}/assets",
    response_model=list[AssetOut],
    dependencies=[Depends(_require_api_key)],
)
def api_list_assets(
    project_id: str,
    type: str | None = None,
    db: Session = Depends(get_db),
) -> list[AssetOut]:
    return jobs_service.list_assets(db, project_id, asset_type=type)


@v1.post(
    "/assets/{asset_id}/review",
    response_model=ReviewOut,
    dependencies=[Depends(_require_api_key)],
)
def api_review_asset(
    asset_id: str, body: ReviewCreate, db: Session = Depends(get_db)
) -> ReviewOut:
    return reviews_service.create_review(db, asset_id, body)


@v1.get(
    "/projects/{project_id}/review-queue",
    response_model=list[ReviewQueueItem],
    dependencies=[Depends(_require_api_key)],
)
def api_review_queue(project_id: str, db: Session = Depends(get_db)) -> list[ReviewQueueItem]:
    return reviews_service.review_queue(db, project_id)


@v1.post(
    "/projects/{project_id}/compose",
    response_model=ComposeOut,
    dependencies=[Depends(_require_api_key)],
)
def api_compose(
    project_id: str, body: ComposeRequest, db: Session = Depends(get_db)
) -> ComposeOut:
    return compose_service.compose_project(db, project_id, body)


@v1.get(
    "/assets/{asset_id}/compliance",
    response_model=ComplianceOut,
    dependencies=[Depends(_require_api_key)],
)
def api_get_compliance(asset_id: str, db: Session = Depends(get_db)) -> ComplianceOut:
    return compose_service.get_compliance(db, asset_id)


@v1.post(
    "/assets/{asset_id}/compliance-stamp",
    response_model=ComplianceOut,
    dependencies=[Depends(_require_api_key)],
)
def api_stamp_compliance(asset_id: str, db: Session = Depends(get_db)) -> ComplianceOut:
    from backend.local_video_studio.compliance import stamp
    from backend.local_video_studio.models import Asset

    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="資產不存在")
    rec = stamp(db, asset=asset, force=True)
    return ComplianceOut(
        id=rec.id,
        asset_id=rec.asset_id,
        explicit_mark=rec.explicit_mark,
        metadata_json=rec.metadata_json,
        watermark_id=rec.watermark_id,
        created_at=rec.created_at,
    )


@v1.get(
    "/projects/{project_id}/resources",
    response_model=ResourceSummary,
    dependencies=[Depends(_require_api_key)],
)
def api_resources(project_id: str, db: Session = Depends(get_db)) -> ResourceSummary:
    return jobs_service.resource_summary(db, project_id)


router.include_router(v1)


def register_local_video_studio(app: FastAPI) -> None:
    init_db()
    app.include_router(router)
