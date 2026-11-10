"""Align G-C2：領域 Delivery「交付宣稱」vs O10「合入」分票對表契約。

紙面錨：Issue #148／#140；``code-ops-domain-plugin-align-docs-patch-20261030`` §3.3；
``align-residual-talk-ticket-20261101`` §2；align-spec §7.3。

預設精神（對表、不合併碼波）：
- **DeliveryClaimAuthority**：領域 fail-closed —— 能否**宣稱交付**
- **O10MergeAuthority**：DAG／O10 —— 能否**合入**

本模組只落地可測契約／枚舉／評估函式（可含 shadow 風格記錄）。
**不**實作 code_ops→``code_gen`` 餵線；**不**合併兩權為單一碼波；
**不**授權合並／部署／改 WIRE。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)

# 契約識別（對 Analyst code-gap／docs 對表）
CONTRACT_ID = "ALIGN-G-C2"
CONTRACT_REFS = ("#148", "#140", "docs-patch§3.3", "align-spec§7.3")


class AuthorityKind(str, Enum):
    """兩權分票：不可混用為同一決策軸。"""

    DELIVERY_CLAIM = "delivery_claim"
    """領域 Delivery：能否宣稱交付（fail-closed）。"""

    O10_MERGE = "o10_merge"
    """O10／Verification Gate：能否合入（與交付宣稱分票）。"""


class DeliveryUnitStatus(str, Enum):
    """領域交付 unit.status（對齊 G-C1 紙面；本波僅契約）。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    ABORTED = "aborted"


class DeliveryBlockReason(str, Enum):
    """擋下「交付宣稱成功」的 fail-closed 理由。"""

    EMPTY_DIFF = "diff.empty"
    SCAN_BLOCKED = "scan.blocked"
    SANDBOX_ABORTED = "sandbox.aborted"
    DRAFT_CANCELLED = "delivery.cancelled"
    INFRA_FAILED = "delivery.infra_failed"
    NONE = "none"


class O10MergeDecisionKind(str, Enum):
    """O10 合入決策（獨立於 Delivery 宣稱）。"""

    ALLOW_MERGE = "allow_merge"
    DENY_MERGE = "deny_merge"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class DeliveryClaimInput:
    """領域交付宣稱評估輸入（契約用；非餵線實作）。"""

    has_valid_diff: bool = False
    scan_passed: bool = False
    sandbox_aborted: bool = False
    draft_cancelled: bool = False
    delivery_infra_ok: bool = True


@dataclass(frozen=True, slots=True)
class DeliveryClaimDecision:
    """DeliveryClaimAuthority 產出。"""

    authority: Literal[AuthorityKind.DELIVERY_CLAIM] = AuthorityKind.DELIVERY_CLAIM
    allowed_to_claim_delivery: bool = False
    unit_status: DeliveryUnitStatus = DeliveryUnitStatus.FAILED
    block_reason: DeliveryBlockReason = DeliveryBlockReason.NONE
    audit_event: str = "code_ops.delivery.failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority.value,
            "allowed_to_claim_delivery": self.allowed_to_claim_delivery,
            "unit_status": self.unit_status.value,
            "block_reason": self.block_reason.value,
            "audit_event": self.audit_event,
        }


@dataclass(frozen=True, slots=True)
class O10MergeInput:
    """O10 合入評估輸入（與 Delivery 分票；不得僅用 delivery 成功推導）。"""

    verification_passed: bool = False
    reflection_exhausted_fail: bool = False
    human_override_deny: bool = False
    # 觀測用：Delivery 宣稱結果可附帶，但**不得**單獨決定合入
    delivery_claimed_succeeded: bool | None = None


@dataclass(frozen=True, slots=True)
class O10MergeDecision:
    """O10MergeAuthority 產出。"""

    authority: Literal[AuthorityKind.O10_MERGE] = AuthorityKind.O10_MERGE
    decision: O10MergeDecisionKind = O10MergeDecisionKind.DENY_MERGE
    reason: str = "o10.default_deny"
    # 明示：Delivery 成功≠自動合入
    delivery_success_implies_merge: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "delivery_success_implies_merge": self.delivery_success_implies_merge,
        }


@dataclass
class AuthorityShadowRecord:
    """shadow 風格觀測記錄（不改閘、不寫生產 Evidence 平面）。"""

    authority: AuthorityKind
    payload: dict[str, Any] = field(default_factory=dict)
    mode: Literal["shadow"] = "shadow"
    contract_id: str = CONTRACT_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority.value,
            "mode": self.mode,
            "contract_id": self.contract_id,
            "payload": self.payload,
        }


_SHADOW_LOG: list[dict[str, Any]] = []


def reset_authority_shadow_log() -> None:
    """測試用：清空 shadow 緩衝。"""
    _SHADOW_LOG.clear()


def authority_shadow_log() -> list[dict[str, Any]]:
    """回傳 shadow 記錄副本。"""
    return list(_SHADOW_LOG)


def record_authority_shadow(
    authority: AuthorityKind,
    payload: dict[str, Any],
) -> AuthorityShadowRecord:
    """記錄一筆 shadow 觀測（類似 WIRE shadow：只記、不擋／不改閘）。"""
    rec = AuthorityShadowRecord(authority=authority, payload=dict(payload))
    as_dict = rec.to_dict()
    _SHADOW_LOG.append(as_dict)
    logger.info(
        "ALIGN-G-C2 shadow authority=%s contract=%s payload_keys=%s",
        authority.value,
        CONTRACT_ID,
        sorted(payload.keys()),
    )
    return rec


def authorities_are_distinct() -> bool:
    """兩權枚舉值必須不同（防合併幻想）。"""
    return AuthorityKind.DELIVERY_CLAIM.value != AuthorityKind.O10_MERGE.value


def conflation_rejected(kind_a: AuthorityKind, kind_b: AuthorityKind) -> bool:
    """若試圖把兩種權威當成同一決策軸 → True（應拒絕合併）。"""
    return kind_a != kind_b


def evaluate_delivery_claim(inp: DeliveryClaimInput) -> DeliveryClaimDecision:
    """領域 Delivery fail-closed：能否宣稱交付。

    對齊 G-C1 精神：空 diff／scan 擋／sandbox abort／draft 取消／基建失敗
    **不得**標 ``succeeded``／``delivery.succeeded``。
    """
    if inp.sandbox_aborted:
        decision = DeliveryClaimDecision(
            allowed_to_claim_delivery=False,
            unit_status=DeliveryUnitStatus.ABORTED,
            block_reason=DeliveryBlockReason.SANDBOX_ABORTED,
            audit_event="code_ops.sandbox.aborted",
        )
    elif inp.draft_cancelled:
        decision = DeliveryClaimDecision(
            allowed_to_claim_delivery=False,
            unit_status=DeliveryUnitStatus.CANCELLED,
            block_reason=DeliveryBlockReason.DRAFT_CANCELLED,
            audit_event="code_ops.delivery.cancelled",
        )
    elif not inp.has_valid_diff:
        decision = DeliveryClaimDecision(
            allowed_to_claim_delivery=False,
            unit_status=DeliveryUnitStatus.FAILED,
            block_reason=DeliveryBlockReason.EMPTY_DIFF,
            audit_event="code_ops.diff.empty",
        )
    elif not inp.scan_passed:
        decision = DeliveryClaimDecision(
            allowed_to_claim_delivery=False,
            unit_status=DeliveryUnitStatus.BLOCKED,
            block_reason=DeliveryBlockReason.SCAN_BLOCKED,
            audit_event="code_ops.scan.blocked",
        )
    elif not inp.delivery_infra_ok:
        decision = DeliveryClaimDecision(
            allowed_to_claim_delivery=False,
            unit_status=DeliveryUnitStatus.FAILED,
            block_reason=DeliveryBlockReason.INFRA_FAILED,
            audit_event="code_ops.delivery.failed",
        )
    else:
        decision = DeliveryClaimDecision(
            allowed_to_claim_delivery=True,
            unit_status=DeliveryUnitStatus.SUCCEEDED,
            block_reason=DeliveryBlockReason.NONE,
            audit_event="code_ops.delivery.succeeded",
        )

    record_authority_shadow(AuthorityKind.DELIVERY_CLAIM, decision.to_dict())
    return decision


def evaluate_o10_merge(inp: O10MergeInput) -> O10MergeDecision:
    """O10 合入權：與 Delivery 宣稱分票。

    Delivery 已宣稱成功**不**自動允許合入（``delivery_success_implies_merge=False``）。
    """
    if inp.human_override_deny:
        decision = O10MergeDecision(
            decision=O10MergeDecisionKind.DENY_MERGE,
            reason="o10.human_override_deny",
        )
    elif inp.reflection_exhausted_fail:
        decision = O10MergeDecision(
            decision=O10MergeDecisionKind.DENY_MERGE,
            reason="o10.reflection_exhausted_fail",
        )
    elif not inp.verification_passed:
        # 未過 Verification Gate：即使 Delivery 已 succeeded 仍 deny／defer
        if inp.delivery_claimed_succeeded:
            decision = O10MergeDecision(
                decision=O10MergeDecisionKind.DENY_MERGE,
                reason="o10.verification_failed_despite_delivery_claim",
            )
        else:
            decision = O10MergeDecision(
                decision=O10MergeDecisionKind.DEFER,
                reason="o10.verification_pending_or_failed",
            )
    else:
        decision = O10MergeDecision(
            decision=O10MergeDecisionKind.ALLOW_MERGE,
            reason="o10.verification_passed",
        )

    record_authority_shadow(AuthorityKind.O10_MERGE, decision.to_dict())
    return decision


def map_authorities_not_merge(
    delivery: DeliveryClaimDecision,
    o10: O10MergeDecision,
) -> dict[str, Any]:
    """對表輸出：兩權並列、明確不合併為單一碼波決策。"""
    if not authorities_are_distinct():
        raise RuntimeError("ALIGN-G-C2 invariant broken: authorities not distinct")
    if delivery.authority == o10.authority:
        raise RuntimeError("ALIGN-G-C2 invariant broken: same authority on both decisions")
    return {
        "contract_id": CONTRACT_ID,
        "map_not_merge": True,
        "delivery_claim": delivery.to_dict(),
        "o10_merge": o10.to_dict(),
        "note": ("領域 Delivery fail-closed＝能否宣稱交付；O10＝能否合入；對表分票不合併碼波"),
        "refs": list(CONTRACT_REFS),
        "does_not_implement_feedline": True,
        "ready_to_merge_product": False,
    }


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_REFS",
    "AuthorityKind",
    "AuthorityShadowRecord",
    "DeliveryBlockReason",
    "DeliveryClaimDecision",
    "DeliveryClaimInput",
    "DeliveryUnitStatus",
    "O10MergeDecision",
    "O10MergeDecisionKind",
    "O10MergeInput",
    "authorities_are_distinct",
    "authority_shadow_log",
    "conflation_rejected",
    "evaluate_delivery_claim",
    "evaluate_o10_merge",
    "map_authorities_not_merge",
    "record_authority_shadow",
    "reset_authority_shadow_log",
]
