"""OPC 內部呼叫權杖。

FASTAPI-AUTH-001：讀寫不對瀏覽器匿名開放。呼叫端帶 X-OPC-Internal，
值來自環境變數 OPC_INTERNAL_TOKEN。未設定時非健康檢查路由一律拒絕。
"""

from __future__ import annotations

import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

HEADER = "x-opc-internal"
_OPEN_PATHS = {"/opc/health"}


def expected_token() -> str:
    return os.getenv("OPC_INTERNAL_TOKEN", "").strip()


def token_matches(supplied: str | None) -> bool:
    expected = expected_token()
    got = (supplied or "").strip()
    if not expected or not got:
        return False
    return hmac.compare_digest(got, expected)


def client_headers() -> dict[str, str]:
    token = expected_token()
    if not token:
        return {}
    return {"X-OPC-Internal": token}


class OpcInternalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS" or request.url.path in _OPEN_PATHS:
            return await call_next(request)
        if not token_matches(request.headers.get(HEADER)):
            return JSONResponse({"detail": "未授權"}, status_code=401)
        return await call_next(request)
