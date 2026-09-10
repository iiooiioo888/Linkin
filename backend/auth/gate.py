"""應用閘門：以 HMAC 摘要比對簽發會話，來源值不進倉庫。

環境變數：
- LINKIN_GATE_ID / LINKIN_GATE_SECRET：覆寫預設摘要對（部署或測試用）
- LINKIN_AUTH_DISABLED=1：關閉閘門
- LINKIN_AUTH_FORCE=1：即使在 pytest 中也強制開啟

靜態站本機核對見 frontend/src/lib/gateDigest.ts（片段須同步）。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any

AUTH_COOKIE = "evoloop_gate"
AUTH_HEADER = "x-linkin-gate"
SESSION_TTL_SEC = 12 * 3600
_FAIL_WINDOW_SEC = 300
_FAIL_LIMIT = 8

_PEPPER = bytes([0x6C, 0x6B, 0x6E, 0x2E, 0x67, 0x61, 0x74, 0x65])

# 預設身分摘要（四段拼接，避免整串出現在單一常數）。
# 產生時請用檔案腳本呼叫 HMAC，勿在殼層一行指令展開 $。
_U = (
    "1f4ac7b757bc42f0",
    "2bafcc236d647a3a",
    "9a11ea1ab69bf25d",
    "77ad23899d26590d",
)
_S = (
    "9a9e35eac9af48e1",
    "4efc7d0d21cbd2ff",
    "e7cc4ec72c0241b3",
    "8bd13f69e5463467",
)
# 單 $ 變體摘要（$$ 在 GitHub／殼層常被吃成一顆）。
_S1 = (
    "d426fee8d6ae4a89",
    "8e30531cbf34787e",
    "00732398331a21f4",
    "5c2728cda013187a",
)

_sessions: dict[str, dict[str, Any]] = {}
_failures: dict[str, list[float]] = {}


def _digest(value: str) -> str:
    return hmac.new(_PEPPER, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _expected_user() -> str:
    override = os.getenv("LINKIN_GATE_ID", "").strip()
    if override:
        return _digest(override)
    return "".join(_U)


def _expected_secret() -> str:
    override = os.getenv("LINKIN_GATE_SECRET", "").strip()
    if override:
        return _digest(override)
    return "".join(_S)


def gate_enabled() -> bool:
    if os.getenv("LINKIN_AUTH_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("LINKIN_AUTH_FORCE", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return not os.getenv("PYTEST_CURRENT_TEST")


def _prune_sessions(now: float) -> None:
    expired = [token for token, rec in _sessions.items() if rec["exp"] <= now]
    for token in expired:
        _sessions.pop(token, None)


def create_session(username: str) -> str:
    now = time.time()
    _prune_sessions(now)
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user": username.strip(),
        "exp": now + SESSION_TTL_SEC,
    }
    return token


def verify_token(token: str | None) -> bool:
    return session_user(token) is not None


def session_user(token: str | None) -> str | None:
    if not token:
        return None
    rec = _sessions.get(token)
    if rec is None:
        return None
    if rec["exp"] <= time.time():
        _sessions.pop(token, None)
        return None
    return str(rec["user"])


def clear_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def extract_token(headers: Any, cookies: Any, query: Any = None) -> str | None:
    header_val = ""
    if headers is not None:
        try:
            header_val = (headers.get(AUTH_HEADER) or headers.get("X-Linkin-Gate") or "").strip()
        except Exception:
            header_val = ""
    if header_val:
        return header_val
    cookie_val = ""
    if cookies is not None:
        try:
            cookie_val = (cookies.get(AUTH_COOKIE) or "").strip()
        except Exception:
            cookie_val = ""
    if cookie_val:
        return cookie_val
    if query is not None:
        try:
            q = (query.get("gate") or "").strip()
        except Exception:
            q = ""
        if q:
            return q
    return None


def ws_authorized(websocket: Any) -> bool:
    if not gate_enabled():
        return True
    token = extract_token(websocket.headers, websocket.cookies, websocket.query_params)
    return verify_token(token)


def _fail_key(identity: str) -> str:
    return identity or "unknown"


def too_many_failures(identity: str) -> bool:
    now = time.time()
    key = _fail_key(identity)
    hits = [t for t in _failures.get(key, []) if now - t < _FAIL_WINDOW_SEC]
    _failures[key] = hits
    return len(hits) >= _FAIL_LIMIT


def record_failure(identity: str) -> None:
    key = _fail_key(identity)
    _failures.setdefault(key, []).append(time.time())


def clear_failures(identity: str) -> None:
    _failures.pop(_fail_key(identity), None)


def issue_login(username: str, secret: str, identity: str = "") -> str | None:
    """校驗通過則回傳會話 token，否則 None。"""
    if too_many_failures(identity):
        return None
    user = (username or "").strip()
    secret = secret or ""
    user_ok = hmac.compare_digest(_digest(user), _expected_user())
    if not user_ok:
        user_ok = hmac.compare_digest(_digest(user.lower()), _expected_user())
    secret_digest = _digest(secret)
    secret_ok = hmac.compare_digest(secret_digest, _expected_secret())
    if not secret_ok and not os.getenv("LINKIN_GATE_SECRET", "").strip():
        secret_ok = hmac.compare_digest(secret_digest, "".join(_S1))
    if not (user_ok and secret_ok):
        record_failure(identity)
        return None
    clear_failures(identity)
    return create_session(user)
