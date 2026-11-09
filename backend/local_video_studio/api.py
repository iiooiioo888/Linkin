"""Local Video Studio HTTP API（M0 health + M1 CRUD）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from backend.local_video_studio import service
from backend.local_video_studio.config import load_config
from backend.local_video_studio.db import get_session_factory, init_db
from backend.local_video_studio.schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
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
        "milestone": "M1",
        "cloud_enabled": cfg.cloud_enabled,
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


router.include_router(v1)


def register_local_video_studio(app: FastAPI) -> None:
    init_db()
    app.include_router(router)
