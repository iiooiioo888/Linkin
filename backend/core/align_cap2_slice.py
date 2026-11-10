"""Align Cap：Cap-2 垂直切片契約（超出 R1 邊界的剩餘契約面）。

紙面錨：Issue #148／#150；``align-residual-talk-ticket-20261101`` §6 Cap；
align-spec Cap-2；QA24 ownership Cap-2（``modelgw_ci_required=false``）。

預設精神（切片契約、非真 runtime）：
- **必須** R1 boundary allow；Cap **不得**覆寫 R1 block／abort
- provider 選型（aider）／fallback 契約面
- draft PR **閘**（契約允許開 draft 的條件；``opens_real_draft_pr=False``）
- Delivery evidence 旗標
- QA24 ownership／``modelgw_ci_required=False``

本模組只落地可測契約／枚舉／評估函式（可含 shadow 風格記錄）。
**不**接真 aider、真 Docker／runsc 起容器、真開 draft PR、
**不**把 24 QA 納 ModelGW CI 必過。
明示：``does_not_wire_real_aider=True``、``does_not_open_real_draft_pr=True``、
``does_not_start_real_runsc=True``、``modelgw_ci_required=False``、
``requires_r1_boundary_allow=True``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)

# 契約識別（對 Analyst code-gap／docs 對表）
CONTRACT_ID = "ALIGN-CAP2"
CONTRACT_REFS = (
    "#148",
    "#150",
    "align-residual§6",
    "align-spec§Cap-2",
    "qa24-skeleton-ownership-Cap-2",
)

# 明示旗標（切片契約 ≠ 真 runtime）
REQUIRES_R1_BOUNDARY_ALLOW = True
DOES_NOT_WIRE_REAL_AIDER = True
DOES_NOT_OPEN_REAL_DRAFT_PR = True
DOES_NOT_START_REAL_RUNSC = True
MODELGW_CI_REQUIRED = False
QA24_OWNERSHIP = "Cap-2"

# 契約預設 provider／fallback
PREFERRED_PROVIDER = "aider"
FALLBACK_PROVIDER = "opencode"


class Cap2Verdict(str, Enum):
    """Cap-2 切片評估結果。"""

    ALLOW = "allow"
    """R1 allow＋切片條件全過；契約上可進 draft 閘評估（不真開 PR）。"""

    BLOCK = "block"
    """切片條件未過／R1 未 allow（block）擋下。"""

    ABORT = "abort"
    """sandbox abort 或 R1 abort → fail-closed；不開 draft。"""


class Cap2BlockReason(str, Enum):
    """擋下／中止理由。"""

    R1_NOT_ALLOW = "cap2.r1_boundary_not_allow"
    R1_ABORT = "cap2.r1_boundary_abort"
    SANDBOX_ABORTED = "cap2.sandbox.aborted"
    SCAN_BLOCKED = "cap2.scan.blocked"
    EMPTY_EVIDENCE = "cap2.evidence.empty"
    PROVIDER_UNAVAILABLE = "cap2.provider.unavailable"
    NONE = "none"


class Cap2Provider(str, Enum):
    """領域 provider 選型（契約面；≠ 模型準入）。"""

    AIDER = "aider"
    OPENCODE = "opencode"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Cap2SliceInput:
    """Cap-2 切片契約評估輸入（非真 runtime）。

    ``r1_boundary_allow``／``r1_verdict``：必須反映 R1 邊界結果。
    Cap **不得**在 R1 block／abort 時自行放行。
    """

    r1_boundary_allow: bool = False
    """R1 邊界是否 allow（布林捷徑）。"""

    r1_verdict: str = ""
    """可選字串 verdict：``allow``／``block``／``abort``（若設則優先於布林）。"""

    preferred_provider: str = PREFERRED_PROVIDER
    """偏好 provider（契約預設 aider）。"""

    aider_available: bool = True
    """aider 是否可用（契約觀測；非真接線）。"""

    fallback_enabled: bool = True
    """aider 不可用時是否允許 fallback 到 opencode。"""

    secret_scan_passed: bool = False
    """secret scan 是否通過（擋 Delivery／draft 閘）。"""

    sandbox_aborted: bool = False
    """sandbox abort → fail-closed；不開 draft。"""

    has_delivery_evidence: bool = False
    """Delivery evidence 是否非空（空 evidence → 不開 draft）。"""

    draft_gate_requested: bool = False
    """是否請求進入 draft PR 閘（契約允許條件評估；不真開）。"""


@dataclass(frozen=True, slots=True)
class Cap2SliceDecision:
    """Align Cap-2 切片評估產出。"""

    verdict: Cap2Verdict = Cap2Verdict.BLOCK
    block_reason: Cap2BlockReason = Cap2BlockReason.NONE
    audit_event: str = "code_ops.cap2.blocked"
    selected_provider: Cap2Provider = Cap2Provider.NONE
    fallback_used: bool = False
    # draft 閘：契約上「允許開 draft」的條件是否滿足（≠ 真開）
    draft_gate_allowed: bool = False
    opens_real_draft_pr: Literal[False] = False
    # 明示旗標
    requires_r1_boundary_allow: Literal[True] = True
    does_not_wire_real_aider: Literal[True] = True
    does_not_open_real_draft_pr: Literal[True] = True
    does_not_start_real_runsc: Literal[True] = True
    modelgw_ci_required: Literal[False] = False
    qa24_ownership: Literal["Cap-2"] = "Cap-2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "block_reason": self.block_reason.value,
            "audit_event": self.audit_event,
            "selected_provider": self.selected_provider.value,
            "fallback_used": self.fallback_used,
            "draft_gate_allowed": self.draft_gate_allowed,
            "opens_real_draft_pr": self.opens_real_draft_pr,
            "requires_r1_boundary_allow": self.requires_r1_boundary_allow,
            "does_not_wire_real_aider": self.does_not_wire_real_aider,
            "does_not_open_real_draft_pr": self.does_not_open_real_draft_pr,
            "does_not_start_real_runsc": self.does_not_start_real_runsc,
            "modelgw_ci_required": self.modelgw_ci_required,
            "qa24_ownership": self.qa24_ownership,
        }


@dataclass
class Cap2ShadowRecord:
    """shadow 風格觀測記錄（不改閘、不寫生產 Evidence 平面）。"""

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


def reset_cap2_shadow_log() -> None:
    """測試用：清空 shadow 緩衝。"""
    _SHADOW_LOG.clear()


def cap2_shadow_log() -> list[dict[str, Any]]:
    """回傳 shadow 記錄副本。"""
    return list(_SHADOW_LOG)


def record_cap2_shadow(payload: dict[str, Any]) -> Cap2ShadowRecord:
    """記錄一筆 shadow 觀測（類似 WIRE shadow：只記、不擋／不改閘）。"""
    rec = Cap2ShadowRecord(payload=dict(payload))
    as_dict = rec.to_dict()
    _SHADOW_LOG.append(as_dict)
    logger.info(
        "ALIGN-CAP2 shadow contract=%s payload_keys=%s",
        CONTRACT_ID,
        sorted(payload.keys()),
    )
    return rec


def _resolve_r1(inp: Cap2SliceInput) -> tuple[bool, str]:
    """解析 R1 邊界結果。

    回傳 ``(allow, normalized_verdict)``。
    若 ``r1_verdict`` 非空則優先；``abort``／``block`` 皆非 allow。
    Cap **不得**覆寫 R1 block／abort。
    """
    raw = (inp.r1_verdict or "").strip().lower()
    if raw:
        if raw == "allow":
            return True, "allow"
        if raw == "abort":
            return False, "abort"
        return False, "block"
    if inp.r1_boundary_allow:
        return True, "allow"
    return False, "block"


def _select_provider(inp: Cap2SliceInput) -> tuple[Cap2Provider, bool, bool]:
    """選型＋fallback 契約。

    回傳 ``(provider, fallback_used, available)``。
    """
    preferred = (inp.preferred_provider or PREFERRED_PROVIDER).strip().lower()
    if preferred == Cap2Provider.AIDER.value and inp.aider_available:
        return Cap2Provider.AIDER, False, True
    if preferred == Cap2Provider.AIDER.value and not inp.aider_available:
        if inp.fallback_enabled:
            return Cap2Provider.OPENCODE, True, True
        return Cap2Provider.NONE, False, False
    if preferred == Cap2Provider.OPENCODE.value:
        return Cap2Provider.OPENCODE, False, True
    # 未知 preferred：若 aider 可用仍選 aider；否則 fallback／不可用
    if inp.aider_available:
        return Cap2Provider.AIDER, False, True
    if inp.fallback_enabled:
        return Cap2Provider.OPENCODE, True, True
    return Cap2Provider.NONE, False, False


def evaluate_cap2_slice(inp: Cap2SliceInput) -> Cap2SliceDecision:
    """評估 Cap-2 切片契約（fail-closed；依賴 R1 allow）。

    順序：R1 abort → R1 not allow → sandbox abort → scan → empty evidence
    → provider 不可用 → allow（可含 draft_gate_allowed；永不真開 PR）。
    """
    r1_allow, r1_norm = _resolve_r1(inp)

    if r1_norm == "abort":
        decision = Cap2SliceDecision(
            verdict=Cap2Verdict.ABORT,
            block_reason=Cap2BlockReason.R1_ABORT,
            audit_event="code_ops.cap2.r1_abort",
            draft_gate_allowed=False,
        )
    elif not r1_allow:
        decision = Cap2SliceDecision(
            verdict=Cap2Verdict.BLOCK,
            block_reason=Cap2BlockReason.R1_NOT_ALLOW,
            audit_event="code_ops.cap2.r1_not_allow",
            draft_gate_allowed=False,
        )
    elif inp.sandbox_aborted:
        decision = Cap2SliceDecision(
            verdict=Cap2Verdict.ABORT,
            block_reason=Cap2BlockReason.SANDBOX_ABORTED,
            audit_event="code_ops.sandbox.aborted",
            draft_gate_allowed=False,
        )
    elif not inp.secret_scan_passed:
        decision = Cap2SliceDecision(
            verdict=Cap2Verdict.BLOCK,
            block_reason=Cap2BlockReason.SCAN_BLOCKED,
            audit_event="code_ops.scan.blocked",
            draft_gate_allowed=False,
        )
    elif not inp.has_delivery_evidence:
        decision = Cap2SliceDecision(
            verdict=Cap2Verdict.BLOCK,
            block_reason=Cap2BlockReason.EMPTY_EVIDENCE,
            audit_event="code_ops.cap2.evidence.empty",
            draft_gate_allowed=False,
        )
    else:
        provider, fallback_used, available = _select_provider(inp)
        if not available:
            decision = Cap2SliceDecision(
                verdict=Cap2Verdict.BLOCK,
                block_reason=Cap2BlockReason.PROVIDER_UNAVAILABLE,
                audit_event="code_ops.cap2.provider.unavailable",
                selected_provider=Cap2Provider.NONE,
                fallback_used=False,
                draft_gate_allowed=False,
            )
        else:
            # 契約 allow：draft 閘僅在請求且條件全過時標 allowed；永不真開
            draft_allowed = bool(inp.draft_gate_requested)
            decision = Cap2SliceDecision(
                verdict=Cap2Verdict.ALLOW,
                block_reason=Cap2BlockReason.NONE,
                audit_event="code_ops.cap2.slice_passed",
                selected_provider=provider,
                fallback_used=fallback_used,
                draft_gate_allowed=draft_allowed,
            )

    record_cap2_shadow(decision.to_dict())
    return decision


def contract_cap2_flags() -> dict[str, Any]:
    """明示本波＝Cap-2 切片契約、非真 runtime／非合並產品。"""
    return {
        "contract_id": CONTRACT_ID,
        "refs": list(CONTRACT_REFS),
        "requires_r1_boundary_allow": REQUIRES_R1_BOUNDARY_ALLOW,
        "does_not_wire_real_aider": DOES_NOT_WIRE_REAL_AIDER,
        "does_not_open_real_draft_pr": DOES_NOT_OPEN_REAL_DRAFT_PR,
        "does_not_start_real_runsc": DOES_NOT_START_REAL_RUNSC,
        "modelgw_ci_required": MODELGW_CI_REQUIRED,
        "qa24_ownership": QA24_OWNERSHIP,
        "preferred_provider": PREFERRED_PROVIDER,
        "fallback_provider": FALLBACK_PROVIDER,
        "does_not_wire_real_runtime": True,
        "ready_to_merge_product": False,
        "beyond_r1_boundary": True,
        "note": (
            "Align Cap＝Cap-2 垂直切片契約（provider／fallback／draft 閘／"
            "Delivery evidence／QA24 ownership）；"
            "須 R1 allow；不接真 aider／真 runsc／真開 draft；"
            "modelgw_ci_required=false"
        ),
    }


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_REFS",
    "DOES_NOT_OPEN_REAL_DRAFT_PR",
    "DOES_NOT_START_REAL_RUNSC",
    "DOES_NOT_WIRE_REAL_AIDER",
    "FALLBACK_PROVIDER",
    "MODELGW_CI_REQUIRED",
    "PREFERRED_PROVIDER",
    "QA24_OWNERSHIP",
    "REQUIRES_R1_BOUNDARY_ALLOW",
    "Cap2BlockReason",
    "Cap2Provider",
    "Cap2ShadowRecord",
    "Cap2SliceDecision",
    "Cap2SliceInput",
    "Cap2Verdict",
    "cap2_shadow_log",
    "contract_cap2_flags",
    "evaluate_cap2_slice",
    "record_cap2_shadow",
    "reset_cap2_shadow_log",
]
