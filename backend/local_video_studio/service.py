"""M1 業務邏輯：專案／鏡頭表／鏡頭 CRUD。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.local_video_studio.models import Project, Script, Shot
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


def _dt(value) -> Any:
    return value


def project_to_out(session: Session, project: Project) -> ProjectOut:
    count = session.scalar(
        select(func.count()).select_from(Shot).where(Shot.project_id == project.id)
    )
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        created_at=_dt(project.created_at),
        shot_count=int(count or 0),
    )


def shot_to_out(shot: Shot) -> ShotOut:
    return ShotOut(
        id=shot.id,
        project_id=shot.project_id,
        scene_no=shot.scene_no,
        shot_no=shot.shot_no,
        description=shot.description,
        dialogue=shot.dialogue,
        duration_sec=float(shot.duration_sec),
        status=shot.status,
        selected_keyframe_asset_id=shot.selected_keyframe_asset_id,
        selected_clip_asset_id=shot.selected_clip_asset_id,
        created_at=_dt(shot.created_at),
    )


def get_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    return project


def create_project(session: Session, body: ProjectCreate) -> ProjectOut:
    project = Project(name=body.name.strip(), description=body.description)
    session.add(project)
    session.flush()
    return project_to_out(session, project)


def list_projects(session: Session) -> list[ProjectOut]:
    rows = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return [project_to_out(session, p) for p in rows]


def get_project(session: Session, project_id: str) -> ProjectOut:
    return project_to_out(session, get_project_or_404(session, project_id))


def patch_project(session: Session, project_id: str, body: ProjectPatch) -> ProjectOut:
    project = get_project_or_404(session, project_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        project.name = data["name"].strip()
    if "description" in data:
        project.description = data["description"]
    if "status" in data and data["status"] is not None:
        project.status = data["status"].strip()
    session.flush()
    return project_to_out(session, project)


def create_shot(session: Session, project_id: str, body: ShotCreate) -> ShotOut:
    get_project_or_404(session, project_id)
    existing = session.scalar(
        select(Shot).where(
            Shot.project_id == project_id,
            Shot.scene_no == body.scene_no,
            Shot.shot_no == body.shot_no,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="鏡頭 scene/shot 編號已存在")
    shot = Shot(
        project_id=project_id,
        scene_no=body.scene_no,
        shot_no=body.shot_no,
        description=body.description,
        dialogue=body.dialogue,
        duration_sec=body.duration_sec,
    )
    session.add(shot)
    session.flush()
    return shot_to_out(shot)


def list_shots(session: Session, project_id: str) -> list[ShotOut]:
    get_project_or_404(session, project_id)
    rows = session.scalars(
        select(Shot)
        .where(Shot.project_id == project_id)
        .order_by(Shot.scene_no.asc(), Shot.shot_no.asc())
    ).all()
    return [shot_to_out(s) for s in rows]


def patch_shot(session: Session, shot_id: str, body: ShotPatch) -> ShotOut:
    shot = session.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="鏡頭不存在")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(shot, key, value)
    session.flush()
    return shot_to_out(shot)


def _upsert_shot_from_script(
    session: Session, project_id: str, item: dict[str, Any]
) -> None:
    try:
        scene_no = int(item["scene_no"])
        shot_no = int(item["shot_no"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"鏡頭表欄位無效：{exc}") from exc
    description = str(item.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="鏡頭 description 必填")
    dialogue = item.get("dialogue")
    duration_raw = item.get("duration_sec", 5)
    try:
        duration_sec = float(duration_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="duration_sec 無效") from exc

    existing = session.scalar(
        select(Shot).where(
            Shot.project_id == project_id,
            Shot.scene_no == scene_no,
            Shot.shot_no == shot_no,
        )
    )
    if existing is None:
        session.add(
            Shot(
                project_id=project_id,
                scene_no=scene_no,
                shot_no=shot_no,
                description=description,
                dialogue=None if dialogue is None else str(dialogue),
                duration_sec=duration_sec,
            )
        )
    else:
        existing.description = description
        existing.dialogue = None if dialogue is None else str(dialogue)
        existing.duration_sec = duration_sec


def upload_script(session: Session, project_id: str, body: ScriptUpload) -> ScriptOut:
    project = get_project_or_404(session, project_id)
    content = body.content_json or {}
    shots_payload = content.get("shots")
    if shots_payload is not None and not isinstance(shots_payload, list):
        raise HTTPException(status_code=422, detail="content_json.shots 須為陣列")

    latest = session.scalar(
        select(func.max(Script.version)).where(Script.project_id == project_id)
    )
    version = int(latest or 0) + 1
    script = Script(project_id=project_id, content_json=content, version=version)
    session.add(script)

    imported = 0
    if isinstance(shots_payload, list):
        for item in shots_payload:
            if not isinstance(item, dict):
                raise HTTPException(status_code=422, detail="shots 項目須為物件")
            _upsert_shot_from_script(session, project_id, item)
            imported += 1

    if project.status == "draft":
        project.status = "scripting"

    session.flush()
    return ScriptOut(
        id=script.id,
        project_id=script.project_id,
        content_json=script.content_json,
        version=script.version,
        created_at=_dt(script.created_at),
        imported_shots=imported,
    )
