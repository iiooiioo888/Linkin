"""計費中間件：綁定 gate 使用者至 contextvars。"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.auth.gate import extract_token, gate_enabled, session_user
from backend.billing.context import billing_user_id, default_anonymous_user


class BillingContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        user = getattr(request.state, "gate_user", None)
        if not user and not gate_enabled():
            user = default_anonymous_user()
        elif not user and gate_enabled():
            token = extract_token(request.headers, request.cookies, request.query_params)
            user = session_user(token)
        billing_token = billing_user_id.set(str(user or "").strip())
        try:
            return await call_next(request)
        finally:
            billing_user_id.reset(billing_token)
