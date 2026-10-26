"""應用閘門：以 HMAC 摘要比對簽發會話。

環境變數：
- LINKIN_GATE_ID / LINKIN_GATE_SECRET：必填。未設定時登入一律拒絕（FASTAPI-AUTH-001）
- LINKIN_AUTH_DISABLED=1：關閉閘門
- LINKIN_AUTH_FORCE=1：即使在 pytest 中也強制開啟

來源值只放在環境變數。前端包不存放可還原的登入秘密（REACT-CONFIG-001）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

AUTH_COOKIE = "evoloop_gate"
AUTH_HEADER = "x-linkin-gate"
SESSION_TTL_SEC = 12 * 3600
_FAIL_WINDOW_SEC = 300
_FAIL_LIMIT = 8

_PEPPER = bytes([0x6C, 0x6B, 0x6E, 0x2E, 0x67, 0x61, 0x74, 0x65])

_sessions: dict[str, dict[str, Any]] = {}
_failures: dict[str, list[float]] = {}


def _digest(value: str) -> str:
    return hmac.new(_PEPPER, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _expected_user() -> str | None:
    override = os.getenv("LINKIN_GATE_ID", "").strip()
    if not override:
        return None
    return _digest(override)


def _expected_secret() -> str | None:
    override = os.getenv("LINKIN_GATE_SECRET", "").strip()
    if not override:
        return None
    return _digest(override)


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


def extract_token(headers: Any, cookies: Any) -> str | None:
    """只接受標頭或 Cookie。查詢字串裡的權杖會進代理日誌（FASTAPI-AUTH-002）。"""
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
    return None


def ws_authorized(websocket: Any) -> bool:
    if not gate_enabled():
        return True
    token = extract_token(websocket.headers, websocket.cookies)
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


def _extra_accounts() -> list[tuple[str, str]]:
    """選用的多帳號清單（``LINKIN_GATE_ACCOUNTS`` 為 JSON 陣列或檔案路徑）。

    每一項 ``{"username", "secret"}``。未設定時仍只接受單一閘門帳密。
    """
    raw = os.getenv("LINKIN_GATE_ACCOUNTS", "").strip()
    if not raw:
        return []
    try:
        if raw.startswith("["):
            data = json.loads(raw)
        else:
            path = Path(raw)
            if not path.is_file():
                return []
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    rows: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        account = str(item.get("username") or "").strip()
        account_secret = str(item.get("secret") or "")
        if account and account_secret:
            rows.append((account, account_secret))
    return rows


def _pair_matches(username: str, secret: str, expect_user: str, expect_secret: str) -> bool:
    user = (username or "").strip()
    user_ok = hmac.compare_digest(_digest(user), _digest(expect_user))
    if not user_ok:
        user_ok = hmac.compare_digest(_digest(user.lower()), _digest(expect_user.lower()))
    secret_ok = hmac.compare_digest(_digest(secret or ""), _digest(expect_secret))
    return bool(user_ok and secret_ok)


def issue_login(username: str, secret: str, identity: str = "") -> str | None:
    """校驗通過則回傳會話 token，否則 None。未設定環境身分時拒絕。"""
    if too_many_failures(identity):
        return None
    expected_user = _expected_user()
    expected_secret = _expected_secret()
    if not expected_user or not expected_secret:
        record_failure(identity)
        return None
    user = (username or "").strip()
    secret = secret or ""
    # 多帳號（master 的 LINEIN_GATE_ACCOUNTS）優先，再比對單一閘門帳密。
    for account, account_secret in _extra_accounts():
        if _pair_matches(user, secret, account, account_secret):
            clear_failures(identity)
            return create_session(account)
    user_ok = hmac.compare_digest(_digest(user), expected_user)
    if not user_ok:
        user_ok = hmac.compare_digest(_digest(user.lower()), expected_user)
    secret_ok = hmac.compare_digest(_digest(secret), expected_secret)
    if not (user_ok and secret_ok):
        record_failure(identity)
        return None
    clear_failures(identity)
    return create_session(user)
