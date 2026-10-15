"""任務租戶可見性。"""

from __future__ import annotations

from backend.tenant.context import current_tenant_user
from backend.tenant.ids import LEGACY_CATALOG_OWNER


def task_owner_user_id(record: object) -> str:
    return str(getattr(record, "user_id", "") or "").strip()


def task_visible_for_tenant(record: object, tenant_id: str | None = None) -> bool:
    owner = task_owner_user_id(record)
    tid = (tenant_id or current_tenant_user()).strip()
    if not owner:
        return tid in {LEGACY_CATALOG_OWNER, "dev", ""}
    return owner == tid
