"""Align R3：AuthGate→tenant 自動注入殘差契約（shadow／紙面邊界；非真接線）。

紙面錨：Issue #148 talk §4；align-spec §10.1 R3；P5／P4 Q7
（AuthGate／session→tenant **自動注入**殘差；本波不做真注入）。

預設精神（契約／shadow only）：
- 來源 ``explicit``／``http_body`` 且 tenant 字串（含 ``""``）→ **allow**（現行口徑）
- 來源 ``authgate_session``／``header_guess``／``cookie`` → **block**／
  ``would_inject_blocked``；shadow 記錄；**不得**回傳「已注入」
- 缺來源且要求 tenant → fail-closed **block**（不猜）
- 異 tenant 交叉嘗試 → **block**

本模組只落地可測契約／枚舉／評估函式（含 shadow 風格記錄）。
**不**接真 AuthGate、**不**改 admit 熱路徑、**不**改 WIRE／環境。
明示：``does_not_wire_real_authgate=True``、``does_not_mutate_admit_hotpath=True``、
``shadow_only=True``、``ready_to_merge_product=False``、``wire_change="none"``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)

# 契約識別（對 Analyst code-gap／docs 對表）
CONTRACT_ID = "ALIGN-R3"
CONTRACT_REFS = (
    "#148",
    "align-residual§4",
    "align-spec§10.1-R3",
    "modelgw-p5-Q7",
)

# 明示旗標（契約 ≠ 真 AuthGate 接線）
DOES_NOT_WIRE_REAL_AUTHGATE = True
DOES_NOT_MUTATE_ADMIT_HOTPATH = True
SHADOW_ONLY = True
WIRE_CHANGE = "none"

# 允許的顯式來源（現行口徑）
ALLOWED_SOURCES = frozenset({"explicit", "http_body"})
# 禁止自動注入來源（Q7 殘差；本波擋下）
BLOCKED_INJECT_SOURCES = frozenset({"authgate_session", "header_guess", "cookie"})


class R3Verdict(str, Enum):
    """R3 tenant 注入邊界評估結果。"""

    ALLOW = "allow"
    """顯式／HTTP body 來源；沿用現行 tenant 字串口徑（含空字串）。"""

    BLOCK = "block"
    """缺來源／異 tenant 等 fail-closed 擋下。"""

    WOULD_INJECT_BLOCKED = "would_inject_blocked"
    """AuthGate／header／cookie 類來源：shadow 記「本會注入」但契約擋下；未注入。"""


class R3BlockReason(str, Enum):
    """擋下理由。"""

    AUTHGATE_SESSION = "r3.authgate_session_blocked"
    HEADER_GUESS = "r3.header_guess_blocked"
    COOKIE = "r3.cookie_blocked"
    MISSING_SOURCE = "r3.missing_source_fail_closed"
    CROSS_TENANT = "r3.cross_tenant_blocked"
    UNKNOWN_SOURCE = "r3.unknown_source_blocked"
    NONE = "none"


class R3TenantSource(str, Enum):
    """tenant 來源分類（契約面）。"""

    EXPLICIT = "explicit"
    HTTP_BODY = "http_body"
    AUTHGATE_SESSION = "authgate_session"
    HEADER_GUESS = "header_guess"
    COOKIE = "cookie"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class R3TenantInjectInput:
    """R3 AuthGate→tenant 注入邊界評估輸入（非真接線）。

    ``tenant_id`` 可為 ``""``（空字串＝現行 C 類口徑）；``None`` 表示未提供。
    ``cross_tenant_id`` 若設且與 ``tenant_id`` 不同 → 異 tenant 交叉擋下。
    """

    source: str = ""
    """來源：``explicit``／``http_body``／``authgate_session``／
    ``header_guess``／``cookie``／空＝missing。"""

    tenant_id: str | None = None
    """顯式／body 帶來的 tenant（允許 ``""``）。"""

    tenant_required: bool = False
    """缺來源時是否要求必有 tenant（是 → fail-closed block）。"""

    cross_tenant_id: str | None = None
    """交叉嘗試的另一 tenant；與 ``tenant_id`` 不同則 block。"""

    would_inject_tenant: str | None = None
    """若走 AuthGate／header／cookie，本會注入的值（僅 shadow 觀測）。"""


@dataclass(frozen=True, slots=True)
class R3TenantInjectDecision:
    """Align R3 評估產出。"""

    verdict: R3Verdict = R3Verdict.BLOCK
    block_reason: R3BlockReason = R3BlockReason.NONE
    audit_event: str = "modelgw.r3.tenant_inject.blocked"
    source_normalized: str = "missing"
    effective_tenant_id: str | None = None
    """allow 時沿用輸入 tenant（可 ``""``）；block／would_inject 不宣稱已注入。"""

    # 恒假：本契約永不宣稱「已注入」
    tenant_injected: Literal[False] = False
    does_not_wire_real_authgate: Literal[True] = True
    does_not_mutate_admit_hotpath: Literal[True] = True
    shadow_only: Literal[True] = True
    wire_change: Literal["none"] = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "block_reason": self.block_reason.value,
            "audit_event": self.audit_event,
            "source_normalized": self.source_normalized,
            "effective_tenant_id": self.effective_tenant_id,
            "tenant_injected": self.tenant_injected,
            "does_not_wire_real_authgate": self.does_not_wire_real_authgate,
            "does_not_mutate_admit_hotpath": self.does_not_mutate_admit_hotpath,
            "shadow_only": self.shadow_only,
            "wire_change": self.wire_change,
        }


@dataclass
class R3ShadowRecord:
    """shadow 風格觀測記錄（不改閘、不改環境、不寫生產平面）。"""

    payload: dict[str, Any] = field(default_factory=dict)
    mode: Literal["shadow"] = "shadow"
    contract_id: str = CONTRACT_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "contract_id": self.contract_id,
            "payload": self.payload,
        }


_SHADOW_LOG: list[dict[str, Any]] = []


def reset_r3_shadow_log() -> None:
    """測試用：清空 shadow 緩衝。"""
    _SHADOW_LOG.clear()


def r3_shadow_log() -> list[dict[str, Any]]:
    """回傳 shadow 記錄副本。"""
    return list(_SHADOW_LOG)


def record_r3_shadow(payload: dict[str, Any]) -> R3ShadowRecord:
    """記錄一筆 shadow 觀測（只記、不擋／不改閘／不改 WIRE）。"""
    rec = R3ShadowRecord(payload=dict(payload))
    as_dict = rec.to_dict()
    _SHADOW_LOG.append(as_dict)
    logger.info(
        "ALIGN-R3 shadow contract=%s payload_keys=%s",
        CONTRACT_ID,
        sorted(payload.keys()),
    )
    return rec


def _normalize_source(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return R3TenantSource.MISSING.value
    if s in ALLOWED_SOURCES or s in BLOCKED_INJECT_SOURCES:
        return s
    return R3TenantSource.UNKNOWN.value


def _inject_block_reason(source: str) -> R3BlockReason:
    if source == R3TenantSource.AUTHGATE_SESSION.value:
        return R3BlockReason.AUTHGATE_SESSION
    if source == R3TenantSource.HEADER_GUESS.value:
        return R3BlockReason.HEADER_GUESS
    if source == R3TenantSource.COOKIE.value:
        return R3BlockReason.COOKIE
    return R3BlockReason.UNKNOWN_SOURCE


def evaluate_r3_tenant_inject(inp: R3TenantInjectInput) -> R3TenantInjectDecision:
    """評估 AuthGate→tenant 注入邊界（契約／shadow；永不真注入）。

    順序：blocked inject 來源 → 異 tenant → 缺來源 fail-closed →
    未知來源 → 顯式／body allow。
    """
    source = _normalize_source(inp.source)

    # 1) AuthGate／header／cookie → would_inject_blocked；不得宣稱已注入
    if source in BLOCKED_INJECT_SOURCES:
        reason = _inject_block_reason(source)
        decision = R3TenantInjectDecision(
            verdict=R3Verdict.WOULD_INJECT_BLOCKED,
            block_reason=reason,
            audit_event="modelgw.r3.tenant_inject.would_inject_blocked",
            source_normalized=source,
            effective_tenant_id=None,
            tenant_injected=False,
        )
    # 2) 異 tenant 交叉（兩端皆有且不同）
    elif (
        inp.cross_tenant_id is not None
        and inp.tenant_id is not None
        and inp.cross_tenant_id != inp.tenant_id
    ):
        decision = R3TenantInjectDecision(
            verdict=R3Verdict.BLOCK,
            block_reason=R3BlockReason.CROSS_TENANT,
            audit_event="modelgw.r3.tenant_inject.cross_tenant_blocked",
            source_normalized=source,
            effective_tenant_id=None,
            tenant_injected=False,
        )
    # 3) 缺來源：要求 tenant → fail-closed；不要求 → 沿用 "" 現行空路徑（仍不猜）
    elif source == R3TenantSource.MISSING.value:
        if inp.tenant_required:
            decision = R3TenantInjectDecision(
                verdict=R3Verdict.BLOCK,
                block_reason=R3BlockReason.MISSING_SOURCE,
                audit_event="modelgw.r3.tenant_inject.missing_source",
                source_normalized=source,
                effective_tenant_id=None,
                tenant_injected=False,
            )
        else:
            # 不猜 AuthGate；有效 tenant 固定 ""（與現網 shadow／C 類相容）
            decision = R3TenantInjectDecision(
                verdict=R3Verdict.ALLOW,
                block_reason=R3BlockReason.NONE,
                audit_event="modelgw.r3.tenant_inject.explicit_ok",
                source_normalized=source,
                effective_tenant_id="",
                tenant_injected=False,
            )
    # 4) 未知來源 → block（不猜）
    elif source == R3TenantSource.UNKNOWN.value:
        decision = R3TenantInjectDecision(
            verdict=R3Verdict.BLOCK,
            block_reason=R3BlockReason.UNKNOWN_SOURCE,
            audit_event="modelgw.r3.tenant_inject.unknown_source",
            source_normalized=source,
            effective_tenant_id=None,
            tenant_injected=False,
        )
    # 5) explicit／http_body → allow（tenant 可為 ""；None 視為 ""）
    else:
        effective = "" if inp.tenant_id is None else inp.tenant_id
        decision = R3TenantInjectDecision(
            verdict=R3Verdict.ALLOW,
            block_reason=R3BlockReason.NONE,
            audit_event="modelgw.r3.tenant_inject.explicit_ok",
            source_normalized=source,
            effective_tenant_id=effective,
            tenant_injected=False,
        )

    # shadow：附帶 would_inject 觀測（不寫環境）
    shadow_payload = decision.to_dict()
    if inp.would_inject_tenant is not None:
        shadow_payload["would_inject_tenant"] = inp.would_inject_tenant
    if inp.cross_tenant_id is not None:
        shadow_payload["cross_tenant_id"] = inp.cross_tenant_id
    record_r3_shadow(shadow_payload)
    return decision


def contract_r3_flags() -> dict[str, Any]:
    """明示本波＝AuthGate→tenant 注入殘差契約／shadow；非真接線、非合並產品。"""
    return {
        "contract_id": CONTRACT_ID,
        "refs": list(CONTRACT_REFS),
        "does_not_wire_real_authgate": DOES_NOT_WIRE_REAL_AUTHGATE,
        "does_not_mutate_admit_hotpath": DOES_NOT_MUTATE_ADMIT_HOTPATH,
        "shadow_only": SHADOW_ONLY,
        "ready_to_merge_product": False,
        "wire_change": WIRE_CHANGE,
        "does_not_claim_injected": True,
        "allowed_sources": sorted(ALLOWED_SOURCES),
        "blocked_inject_sources": sorted(BLOCKED_INJECT_SOURCES),
        "note": (
            "Align R3＝AuthGate→tenant 自動注入殘差契約（shadow only）；"
            "只允許 explicit／http_body；擋 authgate_session／header_guess／cookie；"
            "不接真 AuthGate、不改 admit 熱路徑、不改 WIRE；永不宣稱已注入"
        ),
    }


__all__ = [
    "ALLOWED_SOURCES",
    "BLOCKED_INJECT_SOURCES",
    "CONTRACT_ID",
    "CONTRACT_REFS",
    "DOES_NOT_MUTATE_ADMIT_HOTPATH",
    "DOES_NOT_WIRE_REAL_AUTHGATE",
    "SHADOW_ONLY",
    "WIRE_CHANGE",
    "R3BlockReason",
    "R3ShadowRecord",
    "R3TenantInjectDecision",
    "R3TenantInjectInput",
    "R3TenantSource",
    "R3Verdict",
    "contract_r3_flags",
    "evaluate_r3_tenant_inject",
    "r3_shadow_log",
    "record_r3_shadow",
    "reset_r3_shadow_log",
]
