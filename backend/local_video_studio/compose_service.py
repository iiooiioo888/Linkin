"""專案合成：僅允許已 approve 鏡頭；成功前強制 compliance.stamp。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.local_video_studio.compliance import ComplianceError, stamp
from backend.local_video_studio.ffmpeg_compose import ComposeError, compose_shots
from backend.local_video_studio.models import Asset, GenerationJob, Project, Shot
from backend.local_video_studio.schemas import AssetOut, ComposeOut, ComposeRequest
from backend.local_video_studio.storage import get_storage


def compose_project(session: Session, project_id: str, body: ComposeRequest) -> ComposeOut:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="專案不存在")

    clips: list[str] = []
    for shot_id in body.shot_ids:
        shot = session.get(Shot, shot_id)
        if shot is None or shot.project_id != project_id:
            raise HTTPException(status_code=404, detail=f"鏡頭不存在：{shot_id}")
        if shot.status != "approved":
            raise HTTPException(status_code=409, detail=f"鏡頭未通過審核：{shot_id}")
        asset_id = shot.selected_clip_asset_id
        if not asset_id:
            raise HTTPException(status_code=409, detail=f"鏡頭無成片資產：{shot_id}")
        asset = session.get(Asset, asset_id)
        if asset is None:
            raise HTTPException(status_code=409, detail=f"資產缺失：{asset_id}")
        clips.append(asset.relative_path)

    store = get_storage()
    store.ensure_project_dirs(project_id)
    try:
        result = compose_shots(
            project_id=project_id,
            clip_relative_paths=clips,
            output_name=body.output_name,
            add_watermark=body.add_watermark,
            metadata=body.metadata,
            storage=store,
        )
    except ComposeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = GenerationJob(
        project_id=project_id,
        shot_id=body.shot_ids[0],
        job_type="compose",
        workflow_template="compose_ffmpeg",
        params_json={"shot_ids": body.shot_ids, "output_name": body.output_name},
        status="succeeded",
        attempt=1,
        data_class="local_only",
    )
    session.add(job)
    session.flush()

    final_asset = Asset(
        project_id=project_id,
        shot_id=None,
        type="final",
        relative_path=result["relative_path"],
        mime=result["mime"],
        bytes=result["bytes"],
        sha256=result["sha256"],
    )
    session.add(final_asset)
    session.flush()

    try:
        compliance = stamp(
            session,
            asset=final_asset,
            metadata={
                "ai_generation_params": body.metadata,
                "engine": result["engine"],
                "clips": clips,
            },
        )
    except ComplianceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 不可繞過：無 compliance 則視為失敗
    if compliance is None or not compliance.explicit_mark:
        raise HTTPException(status_code=500, detail="compliance.stamp 失敗")

    project = session.get(Project, project_id)
    if project is not None:
        project.status = "composing"

    return ComposeOut(
        job_id=job.id,
        asset=AssetOut(
            id=final_asset.id,
            project_id=final_asset.project_id,
            shot_id=final_asset.shot_id,
            type=final_asset.type,
            relative_path=final_asset.relative_path,
            mime=final_asset.mime,
            bytes=final_asset.bytes,
            sha256=final_asset.sha256,
            created_at=final_asset.created_at,
        ),
        compliance_id=compliance.id,
        relative_path=final_asset.relative_path,
        engine=result["engine"],
    )


def get_compliance(session: Session, asset_id: str):
    from backend.local_video_studio.models import ComplianceRecord
    from backend.local_video_studio.schemas import ComplianceOut

    row = session.scalar(select(ComplianceRecord).where(ComplianceRecord.asset_id == asset_id))
    if row is None:
        raise HTTPException(status_code=404, detail="無合規記錄")
    return ComplianceOut(
        id=row.id,
        asset_id=row.asset_id,
        explicit_mark=row.explicit_mark,
        metadata_json=row.metadata_json,
        watermark_id=row.watermark_id,
        created_at=row.created_at,
    )
