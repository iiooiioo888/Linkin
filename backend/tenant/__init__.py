"""多租戶執行期：以 gate 使用者 ID 為租戶鍵。"""

from backend.tenant.context import current_tenant_user, require_tenant_user, tenant_user_id
from backend.tenant.ids import LEGACY_CATALOG_OWNER

__all__ = [
    "LEGACY_CATALOG_OWNER",
    "current_tenant_user",
    "require_tenant_user",
    "tenant_user_id",
]
