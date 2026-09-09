"""HTTP 閘門中間件：未持有效會話則拒絕（預檢與公開探針除外）。"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.auth.gate import extract_token, gate_enabled, session_user, verify_token

_OPEN_EXACT = {
    "/health",
    "/healthz",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/auth/login",
    "/auth/logout",
    # 對外 MCP server：自帶 Bearer EVOL_MCP_SERVER_TOKEN 驗證（fail-closed）
    "/mcp-server",
}
_OPEN_PREFIX = ("/docs", "/redoc")


def _is_open(path: str) -> bool:
    if path in _OPEN_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _OPEN_PREFIX)


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS" or not gate_enabled() or _is_open(request.url.path):
            return await call_next(request)
        token = extract_token(request.headers, request.cookies, request.query_params)
        if not verify_token(token):
            return JSONResponse({"detail": "未登入或會話已失效"}, status_code=401)
        request.state.gate_user = session_user(token)
        return await call_next(request)
