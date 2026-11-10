"""健康檢查與登入閘門 API（自 backend.main 抽出）。

GET /health、POST /auth/login、GET /auth/me、POST /auth/logout。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.api.security import _clear_gate_cookie, _client_identity, _set_gate_cookie
from backend.auth.gate import (
    clear_session,
    extract_token,
    issue_login,
    session_user,
)

router = APIRouter(tags=["health-auth"])


class GateLoginBody(BaseModel):
    username: str = ""
    password: str = ""


@router.get("/health")
async def health():
    from backend.core.opc_degrade import opc_health_view

    opc = opc_health_view()
    return {
        "status": "ok",
        "degraded": opc["opc_status"] == "unavailable",
        "opc": opc,
    }


@router.post("/auth/login")
async def auth_login(body: GateLoginBody, request: Request):
    token = issue_login(body.username, body.password, identity=_client_identity(request))
    if not token:
        raise HTTPException(status_code=401, detail="帳號或密碼不正確")
    resp = JSONResponse({"ok": True, "user": body.username.strip()})
    _set_gate_cookie(resp, token, request)
    return resp


@router.get("/auth/me")
async def auth_me(request: Request):
    token = extract_token(request.headers, request.cookies)
    user = session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="未登入或會話已失效")
    return {"ok": True, "user": user}


@router.post("/auth/logout")
async def auth_logout(request: Request):
    token = extract_token(request.headers, request.cookies)
    clear_session(token)
    resp = JSONResponse({"ok": True})
    _clear_gate_cookie(resp, request)
    return resp
