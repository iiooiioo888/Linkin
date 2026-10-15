"""HTTP 租戶守衛（供 FastAPI 路由使用）。"""

from __future__ import annotations

from fastapi import HTTPException

from backend.services.task_manager import TaskRecord, task_manager


def require_tenant_http() -> str:
    from backend.tenant.context import require_tenant_user

    try:
        return require_tenant_user()
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def task_record_or_404(task_id: str) -> TaskRecord:
    record = task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return record
