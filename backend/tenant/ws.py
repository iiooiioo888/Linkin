"""WebSocket 租戶／計費上下文綁定。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from backend.auth.gate import extract_token, gate_enabled, session_user
from backend.billing.context import billing_user_id, default_anonymous_user
from backend.tenant.context import tenant_user_id


@asynccontextmanager
async def websocket_tenant_scope(websocket: Any) -> AsyncIterator[str]:
    """從 WS cookie／header 解析 gate 使用者並綁定 tenant／billing contextvars。"""
    token = extract_token(websocket.headers, websocket.cookies)
    user = session_user(token)
    if not user and not gate_enabled():
        user = default_anonymous_user()
    uid = str(user or "").strip()
    t_tenant = tenant_user_id.set(uid)
    t_billing = billing_user_id.set(uid)
    try:
        yield uid
    finally:
        tenant_user_id.reset(t_tenant)
        billing_user_id.reset(t_billing)
