"""護欄決策簽章。適配器只接受 verdict=allow 的 HMAC。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from linkin_core.contracts.minecraft import MUTATING_MINECRAFT_ACTIONS
from linkin_core.contracts.version import SCHEMA_VERSION

POLICY_VERSION = "2026-10-26"
SENSITIVE_TOOLS = frozenset({"opc_write", "opc.write", *MUTATING_MINECRAFT_ACTIONS})
DEFAULT_KID = "v1"

# nonce 重放防護（進程內；正式可換 Redis）
_USED_NONCES: dict[str, float] = {}


def is_sensitive(tool: str) -> bool:
    return tool in SENSITIVE_TOOLS


def args_hash(args: dict[str, Any]) -> str:
    body = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def signing_key() -> bytes:
    raw = os.getenv("LINKIN_GUARDRAIL_HMAC_KEY", "").strip()
    if not raw:
        raise RuntimeError("LINKIN_GUARDRAIL_HMAC_KEY 未設定")
    return raw.encode("utf-8")


def key_id() -> str:
    return os.getenv("LINKIN_GUARDRAIL_HMAC_KID", DEFAULT_KID).strip() or DEFAULT_KID


def new_nonce() -> str:
    return secrets.token_hex(16)


def reset_nonce_store() -> None:
    _USED_NONCES.clear()


def _purge_expired_nonces(now: float) -> None:
    expired = [nonce for nonce, exp in _USED_NONCES.items() if exp < now]
    for nonce in expired:
        del _USED_NONCES[nonce]


def issue_token(claims: dict[str, Any]) -> str:
    enriched = dict(claims)
    enriched.setdefault("kid", key_id())
    enriched.setdefault("nonce", new_nonce())
    body = json.dumps(enriched, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(signing_key(), body, hashlib.sha256).hexdigest()
    blob = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{blob}.{signature}"


def verify_token(
    token: str,
    *,
    tenant_id: str | None = None,
    consume_nonce: bool = True,
) -> dict[str, Any]:
    if not token or "." not in token:
        raise ValueError("簽章格式無效")
    blob, signature = token.split(".", 1)
    padded = blob + "=" * (-len(blob) % 4)
    try:
        body = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ValueError("簽章格式無效") from exc
    expected = hmac.new(signing_key(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("簽章不符")
    claims = json.loads(body.decode("utf-8"))
    now = time.time()
    if float(claims.get("exp") or 0) < now:
        raise ValueError("決策已過期")
    if claims.get("verdict") != "allow":
        raise ValueError("決策未放行")
    if claims.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("契約版本不符")
    kid = claims.get("kid")
    if not kid or not isinstance(kid, str):
        raise ValueError("缺少 kid")
    if kid != key_id():
        raise ValueError("kid 不符")
    nonce = claims.get("nonce")
    if not nonce or not isinstance(nonce, str):
        raise ValueError("缺少 nonce")
    if tenant_id is not None and claims.get("tenant_id") != tenant_id:
        raise ValueError("跨租戶拒絕")
    if consume_nonce:
        _purge_expired_nonces(now)
        if nonce in _USED_NONCES:
            raise ValueError("nonce 重放")
        _USED_NONCES[nonce] = float(claims.get("exp") or now)
    return claims
