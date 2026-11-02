"""Align R1：runsc／沙箱硬邊界＝Cap-2 碼波**邊界**契約（非全量 Cap-2）。

紙面錨：Issue #148／#140；``align-residual-talk-ticket-20261101`` §3；
align-spec §3 可保留沙箱硬邊界、§7.2、§10.1 R1。

預設精神（邊界落地、不兌現全量）：
- runtime 必須 ``runsc``
- ``network=none``
- token／secret **不**進沙箱
- secret scan 擋 Delivery
- sandbox abort → fail-closed（不開 draft）

本模組只落地可測契約／枚舉／評估函式（可含 shadow 風格記錄）。
**不**實作 aider、真 Docker／runsc 起容器、draft PR 自動開、24 QA 納 ModelGW CI。
明示：``cap2_boundary_only=True``、``does_not_implement_full_cap2=True``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)

# 契約識別（對 Analyst code-gap／docs 對表）
CONTRACT_ID = "ALIGN-R1"
CONTRACT_REFS = ("#148", "#140", "align-residual§3", "align-spec§7.2", "align-spec§10.1-R1")

# 邊界旗標（談結≠已兌現 Cap-2 全量）
CAP2_BOUNDARY_ONLY = True
DOES_NOT_IMPLEMENT_FULL_CAP2 = True

REQUIRED_RUNTIME = "runsc"
REQUIRED_NETWORK = "none"


class SandboxVerdict(str, Enum):
    """沙箱邊界評估結果。"""

    ALLOW = "allow"
    """硬邊界全過；可進入後續 Delivery 評估（本契約不開 draft）。"""

    BLOCK = "block"
    """硬邊界違規擋下（network／token／scan 等）。"""

    ABORT = "abort"
    """sandbox abort → fail-closed；不開 draft。"""


class SandboxBlockReason(str, Enum):
    """擋下／中止理由。"""

    RUNTIME_NOT_RUNSC = "sandbox.runtime_not_runsc"
    NETWORK_NOT_NONE = "sandbox.network_not_none"
    TOKEN_INTO_SANDBOX = "sandbox.token_into_sandbox"
    SECRET_INTO_SANDBOX = "sandbox.secret_into_sandbox"
    SCAN_BLOCKED = "sandbox.scan.blocked"
    SANDBOX_ABORTED = "sandbox.aborted"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SandboxBoundaryInput:
    """沙箱硬邊界評估輸入（契約用；非真起容器）。"""

    runtime: str = ""
    """預期 ``runsc``。"""

    network: str = ""
    """預期 ``none``（``network=none``）。"""

    token_in_sandbox: bool = False
    """token 是否進沙箱（必須 False）。"""

    secret_in_sandbox: bool = False
    """secret 是否進沙箱（必須 False）。"""

    secret_scan_passed: bool = False
    """secret scan 是否通過（擋 Delivery）。"""

    sandbox_aborted: bool = False
    """sandbox abort → fail-closed；不開 draft。"""


@dataclass(frozen=True, slots=True)
class SandboxBoundaryDecision:
    """Align R1 沙箱硬邊界評估產出。"""

    verdict: SandboxVerdict = SandboxVerdict.BLOCK
    block_reason: SandboxBlockReason = SandboxBlockReason.NONE
    audit_event: str = "code_ops.sandbox.blocked"
    # 明示邊界口径
    cap2_boundary_only: Literal[True] = True
    does_not_implement_full_cap2: Literal[True] = True
    opens_draft_pr: Literal[False] = False
    """abort／block 均不開 draft；allow 本契約亦不自動開。"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "block_reason": self.block_reason.value,
            "audit_event": self.audit_event,
            "cap2_boundary_only": self.cap2_boundary_only,
            "does_not_implement_full_cap2": self.does_not_implement_full_cap2,
            "opens_draft_pr": self.opens_draft_pr,
        }


@dataclass
class SandboxShadowRecord:
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


def reset_sandbox_shadow_log() -> None:
    """測試用：清空 shadow 緩衝。"""
    _SHADOW_LOG.clear()


def sandbox_shadow_log() -> list[dict[str, Any]]:
    """回傳 shadow 記錄副本。"""
    return list(_SHADOW_LOG)


def record_sandbox_shadow(payload: dict[str, Any]) -> SandboxShadowRecord:
    """記錄一筆 shadow 觀測（類似 WIRE shadow：只記、不擋／不改閘）。"""
    rec = SandboxShadowRecord(payload=dict(payload))
    as_dict = rec.to_dict()
    _SHADOW_LOG.append(as_dict)
    logger.info(
        "ALIGN-R1 shadow contract=%s payload_keys=%s",
        CONTRACT_ID,
        sorted(payload.keys()),
    )
    return rec


def evaluate_sandbox_boundary(inp: SandboxBoundaryInput) -> SandboxBoundaryDecision:
    """評估沙箱硬邊界（fail-closed）。

    順序：abort → runtime → network → token → secret → scan → allow。
    """
    if inp.sandbox_aborted:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.ABORT,
            block_reason=SandboxBlockReason.SANDBOX_ABORTED,
            audit_event="code_ops.sandbox.aborted",
        )
    elif inp.runtime != REQUIRED_RUNTIME:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.BLOCK,
            block_reason=SandboxBlockReason.RUNTIME_NOT_RUNSC,
            audit_event="code_ops.sandbox.runtime_blocked",
        )
    elif inp.network != REQUIRED_NETWORK:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.BLOCK,
            block_reason=SandboxBlockReason.NETWORK_NOT_NONE,
            audit_event="code_ops.sandbox.network_blocked",
        )
    elif inp.token_in_sandbox:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.BLOCK,
            block_reason=SandboxBlockReason.TOKEN_INTO_SANDBOX,
            audit_event="code_ops.sandbox.token_blocked",
        )
    elif inp.secret_in_sandbox:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.BLOCK,
            block_reason=SandboxBlockReason.SECRET_INTO_SANDBOX,
            audit_event="code_ops.sandbox.secret_blocked",
        )
    elif not inp.secret_scan_passed:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.BLOCK,
            block_reason=SandboxBlockReason.SCAN_BLOCKED,
            audit_event="code_ops.sandbox.scan.blocked",
        )
    else:
        decision = SandboxBoundaryDecision(
            verdict=SandboxVerdict.ALLOW,
            block_reason=SandboxBlockReason.NONE,
            audit_event="code_ops.sandbox.boundary_passed",
        )

    record_sandbox_shadow(decision.to_dict())
    return decision


def contract_boundary_flags() -> dict[str, Any]:
    """明示本波僅 Cap-2 邊界、非全量實作。"""
    return {
        "contract_id": CONTRACT_ID,
        "refs": list(CONTRACT_REFS),
        "cap2_boundary_only": CAP2_BOUNDARY_ONLY,
        "does_not_implement_full_cap2": DOES_NOT_IMPLEMENT_FULL_CAP2,
        "required_runtime": REQUIRED_RUNTIME,
        "required_network": REQUIRED_NETWORK,
        "does_not_implement_aider": True,
        "does_not_start_real_runsc_container": True,
        "does_not_auto_open_draft_pr": True,
        "does_not_include_qa24_in_modelgw_ci": True,
        "ready_to_merge_product": False,
        "note": (
            "Align R1＝沙箱硬邊界契約落地；"
            "談結≠已兌現 Cap-2 全量（無 aider／真 runsc／draft 自動開／QA24→ModelGW CI）"
        ),
    }


__all__ = [
    "CAP2_BOUNDARY_ONLY",
    "CONTRACT_ID",
    "CONTRACT_REFS",
    "DOES_NOT_IMPLEMENT_FULL_CAP2",
    "REQUIRED_NETWORK",
    "REQUIRED_RUNTIME",
    "SandboxBlockReason",
    "SandboxBoundaryDecision",
    "SandboxBoundaryInput",
    "SandboxShadowRecord",
    "SandboxVerdict",
    "contract_boundary_flags",
    "evaluate_sandbox_boundary",
    "record_sandbox_shadow",
    "reset_sandbox_shadow_log",
    "sandbox_shadow_log",
]
