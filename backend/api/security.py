"""登入閘門的來源識別與 Cookie 設定（自 backend.main 抽出）。

`backend.main` 會 re-export 這些名稱（含底線），`backend/tests/test_auth_gate.py`
以 `from backend.main import _client_identity` 取用，請勿改動函式名稱與簽名。
"""

import ipaddress
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.auth.gate import AUTH_COOKIE, SESSION_TTL_SEC

# 只認這些網段是「本機反向代理」；其餘一律視為外部直連。
_TRUSTED_PROXY_NETS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def _is_local_peer(peer: str) -> bool:
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXY_NETS if net.version == addr.version)


def _client_identity(request: Request) -> str:
    """真實來源 IP：只有對端是內網／本機（反向代理）時才信任轉發標頭。

    nginx 以 $remote_addr 覆寫 X-Real-IP，X-Forwarded-For 則是附加模式
    （$proxy_add_x_forwarded_for），客戶端塞的假值會留在前面，最後一跳才是真實來源。
    直接連進來的公網對端一律忽略標頭，避免用假 XFF 繞過登入失敗次數限制。
    """
    peer = request.client.host if request.client else ""
    if peer and _is_local_peer(peer):
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real
        hops = [
            hop.strip()
            for hop in (request.headers.get("x-forwarded-for") or "").split(",")
            if hop.strip()
        ]
        if hops:
            return hops[-1]
    return peer


def _cookie_secure(request: Request) -> bool:
    """FASTAPI-SESS-001：只有 HTTPS 才加 Secure。本機 HTTP 不加，否則瀏覽器會丟掉登入 Cookie。"""
    flag = os.getenv("LINKIN_COOKIE_SECURE", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    forwarded = (request.headers.get("x-forwarded-proto") or request.url.scheme or "")
    proto = forwarded.split(",")[0].strip().lower()
    return proto == "https"


def _set_gate_cookie(response: JSONResponse, token: str, request: Request) -> None:
    # REACT-AUTH-001：權杖只放 HttpOnly Cookie，不進 JSON，腳本讀不到。
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=SESSION_TTL_SEC,
        httponly=True,
        samesite="lax",
        path="/",
        secure=_cookie_secure(request),
    )


def _clear_gate_cookie(response: JSONResponse, request: Request) -> None:
    response.delete_cookie(
        AUTH_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
    )
