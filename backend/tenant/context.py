"""租戶 contextvars：與 gate／計費使用者對齊。"""

from __future__ import annotations

import contextvars
import re

tenant_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_user_id", default="")


def _sanitize_tenant_id(raw: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._@-]+", "_", (raw or "").strip())[:96]
    return text or "anonymous"


def current_tenant_user() -> str:
    """當前請求／任務的租戶鍵；pytest 無 gate 時回退計費匿名使用者。"""
    explicit = (tenant_user_id.get() or "").strip()
    if explicit:
        return _sanitize_tenant_id(explicit)
    from backend.billing.context import current_billing_user, default_anonymous_user

    return _sanitize_tenant_id(current_billing_user() or default_anonymous_user())


def require_tenant_user() -> str:
    uid = current_tenant_user()
    if not uid or uid == "anonymous":
        raise PermissionError("未登入或租戶無效")
    return uid
