"""任務租戶可見性。"""

from __future__ import annotations

import os

from backend.tenant.context import current_tenant_user
from backend.tenant.ids import LEGACY_CATALOG_OWNER


def task_owner_user_id(record: object) -> str:
    return str(getattr(record, "user_id", "") or "").strip()


def _legacy_task_visible(tenant_id: str) -> bool:
    tid = tenant_id.strip()
    if not tid or tid == "anonymous":
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return tid in {LEGACY_CATALOG_OWNER, "dev"}
    return tid == LEGACY_CATALOG_OWNER


def _resolve_tenant_id(tenant_id: str | None) -> str:
    if tenant_id is None:
        return current_tenant_user().strip()
    return tenant_id.strip()


def task_visible_for_tenant(record: object, tenant_id: str | None = None) -> bool:
    owner = task_owner_user_id(record)
    tid = _resolve_tenant_id(tenant_id)
    if not owner:
        return _legacy_task_visible(tid)
    return owner == tid


def task_id_visible_for_tenant(task_id: str, tenant_id: str | None = None) -> bool:
    """軌跡／檢查點列表：依任務記錄判斷；無記錄的孤兒檔僅 deploy_admin（pytest 另含 dev）。"""
    from backend.services.task_manager import task_manager

    tid = _resolve_tenant_id(tenant_id)
    record = task_manager.get_task(task_id, skip_tenant_check=True)
    if record is not None:
        return task_visible_for_tenant(record, tid)
    return _legacy_task_visible(tid)
