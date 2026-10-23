"""HTTP 閘門中間件：未持有效會話則拒絕（預檢與公開探針除外）。"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.auth.gate import extract_token, gate_enabled, session_user, verify_token

# FASTAPI-OPENAPI-001：/docs、/redoc、/openapi.json 不在公開名單。
# 需要文件時設 LINKIN_ENABLE_DOCS=1，且仍要先登入。
_OPEN_EXACT = {
    "/health",
    "/healthz",
    "/favicon.ico",
    "/auth/login",
    "/auth/logout",
    # 對外 MCP server：自帶 Bearer EVOL_MCP_SERVER_TOKEN 驗證（fail-closed）
    "/mcp-server",
}


def _is_open(path: str) -> bool:
    return path in _OPEN_EXACT


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS" or not gate_enabled() or _is_open(request.url.path):
            return await call_next(request)
        token = extract_token(request.headers, request.cookies)
        if not verify_token(token):
            return JSONResponse({"detail": "未登入或會話已失效"}, status_code=401)
        request.state.gate_user = session_user(token)
        return await call_next(request)
