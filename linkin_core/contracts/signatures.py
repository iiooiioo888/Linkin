"""護欄決策簽章。適配器只接受 verdict=allow 的 HMAC。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from linkin_core.contracts.minecraft import MUTATING_MINECRAFT_ACTIONS
from linkin_core.contracts.version import SCHEMA_VERSION

POLICY_VERSION = "2026-10-26"
SENSITIVE_TOOLS = frozenset({"opc_write", "opc.write", *MUTATING_MINECRAFT_ACTIONS})


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


def issue_token(claims: dict[str, Any]) -> str:
    body = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(signing_key(), body, hashlib.sha256).hexdigest()
    blob = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{blob}.{signature}"


def verify_token(token: str) -> dict[str, Any]:
    blob, signature = token.split(".", 1)
    padded = blob + "=" * (-len(blob) % 4)
    body = base64.urlsafe_b64decode(padded.encode("ascii"))
    expected = hmac.new(signing_key(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("簽章不符")
    claims = json.loads(body.decode("utf-8"))
    if float(claims.get("exp") or 0) < time.time():
        raise ValueError("決策已過期")
    if claims.get("verdict") != "allow":
        raise ValueError("決策未放行")
    if claims.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("契約版本不符")
    return claims
