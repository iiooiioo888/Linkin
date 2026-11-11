"""P0-03：Workflow 模板匯入、mapping 校驗、版本記錄。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.local_video_studio.models import WorkflowTemplate
from backend.local_video_studio.schemas import WorkflowTemplateImport, WorkflowTemplateOut
from backend.local_video_studio.workflow_inject import WorkflowMappingError, inject_params

_WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,126}$")


def _to_out(row: WorkflowTemplate) -> WorkflowTemplateOut:
    return WorkflowTemplateOut(
        id=row.id,
        name=row.name,
        version=row.version,
        json_path=row.json_path,
        mapping_path=row.mapping_path,
        required_models=list(row.required_models_json or []),
        notes=row.notes,
        created_at=row.created_at,
    )


def validate_mapping_against_workflow(
    workflow_json: dict[str, Any],
    mapping_json: dict[str, Any],
) -> None:
    """用空 params 走一遍 mapping；缺 node／input 即失敗。"""
    try:
        inject_params(workflow_json, {}, mapping_json)
    except WorkflowMappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # 再以 dummy 值確認每個 mapped node 可寫
    entries = mapping_json.get("mappings") or []
    dummy: dict[str, Any] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("param"):
            dummy[str(entry["param"])] = "__lvs_validate__"
    try:
        inject_params(workflow_json, dummy, mapping_json)
    except WorkflowMappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def import_workflow(session: Session, body: WorkflowTemplateImport) -> WorkflowTemplateOut:
    name = (body.name or "").strip()
    if not _NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="模板名稱僅允許字母數字、底線、連字號，且須以字母數字開頭",
        )
    if not isinstance(body.workflow_json, dict) or not body.workflow_json:
        raise HTTPException(status_code=422, detail="workflow_json 須為非空物件（ComfyUI API 格式）")
    if not isinstance(body.mapping_json, dict):
        raise HTTPException(status_code=422, detail="mapping_json 須為物件")

    validate_mapping_against_workflow(body.workflow_json, body.mapping_json)

    latest = session.scalar(
        select(func.max(WorkflowTemplate.version)).where(WorkflowTemplate.name == name)
    )
    version = int(latest or 0) + 1

    # 落盤到 workflows/imported/（可選追溯；DB blob 為真相）
    imported_dir = _WORKFLOWS_DIR / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    map_dir = imported_dir / "mappings"
    map_dir.mkdir(parents=True, exist_ok=True)
    json_path = f"imported/{name}.v{version}.json"
    mapping_path = f"imported/mappings/{name}.v{version}.mapping.json"
    (_WORKFLOWS_DIR / json_path).write_text(
        json.dumps(body.workflow_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (_WORKFLOWS_DIR / mapping_path).write_text(
        json.dumps(body.mapping_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    row = WorkflowTemplate(
        name=name,
        version=version,
        json_path=json_path,
        mapping_path=mapping_path,
        workflow_json=body.workflow_json,
        mapping_json=body.mapping_json,
        required_models_json=list(body.required_models or []),
        notes=body.notes,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


def list_workflows(
    session: Session, *, name: str | None = None, latest_only: bool = False
) -> list[WorkflowTemplateOut]:
    stmt = select(WorkflowTemplate).order_by(
        WorkflowTemplate.name.asc(), WorkflowTemplate.version.desc()
    )
    if name:
        stmt = stmt.where(WorkflowTemplate.name == name)
    rows = list(session.scalars(stmt).all())
    if not latest_only:
        return [_to_out(r) for r in rows]
    seen: set[str] = set()
    out: list[WorkflowTemplateOut] = []
    for row in rows:
        if row.name in seen:
            continue
        seen.add(row.name)
        out.append(_to_out(row))
    return out


def get_workflow(
    session: Session, name: str, *, version: int | None = None
) -> WorkflowTemplateOut:
    row = _get_row(session, name, version=version)
    return _to_out(row)


def _get_row(
    session: Session, name: str, *, version: int | None = None
) -> WorkflowTemplate:
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.name == name)
    if version is not None:
        stmt = stmt.where(WorkflowTemplate.version == version)
    else:
        stmt = stmt.order_by(WorkflowTemplate.version.desc())
    row = session.scalars(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"工作流模板不存在：{name}")
    return row


def load_template_payload(
    session: Session,
    name: str,
    *,
    version: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], int | None, list[str]]:
    """優先 DB；否則讀倉內 workflows/{name}.json。

    回傳 (workflow_json, mapping_json, version_or_None, required_models)。
    """
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.name == name)
    if version is not None:
        stmt = stmt.where(WorkflowTemplate.version == version)
    else:
        stmt = stmt.order_by(WorkflowTemplate.version.desc())
    row = session.scalars(stmt).first()
    if row is not None:
        return (
            dict(row.workflow_json),
            dict(row.mapping_json),
            int(row.version),
            [str(x) for x in (row.required_models_json or [])],
        )

    wf_path = _WORKFLOWS_DIR / f"{name}.json"
    map_path = _WORKFLOWS_DIR / "mappings" / f"{name}.mapping.json"
    if not wf_path.is_file():
        raise FileNotFoundError(f"workflow 不存在：{wf_path}")
    if not map_path.is_file():
        raise FileNotFoundError(f"mapping 不存在：{map_path}")
    return (
        json.loads(wf_path.read_text(encoding="utf-8")),
        json.loads(map_path.read_text(encoding="utf-8")),
        None,
        [],
    )
