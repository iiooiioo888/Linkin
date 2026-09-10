"""L1 憲兵攔截仲裁（TODO §2.4／契約 C-SEAT-006）。

契約（寫死）：
- L1 攔截（REWORK 耗盡／ESCALATE）後，執行席（L2）或指揮席（L3）**不得自行推翻**；
  爭議一律升級至 **L5 用戶決策或人工干預**（顯式 API／UI）。
- 每次仲裁留下**可觀測決策記錄**（``STORE`` 節點 kind=``l1_arbitration``＋待決列）。

因此本模組**刻意不提供**任何 ``override_*``／``force_*`` 入口：
執行席唯一合法路徑是 :func:`raise_l1_dispute` → L5 裁決 → :func:`apply_ruling`。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import EscalationChoice, RahoLayer
from backend.company.raho.store import STORE

ARBITRATION_KIND = "l1_arbitration"

# 裁決選項（寫死）：只有 L5／人工能選，執行席無此權限
RULING_ACCEPT_L1 = "accept_l1"      # 接受 L1 攔截：重做或調整規格
RULING_LOWER_STANDARD = "lower_standard"  # L5 明示降低驗收標準（留痕）
RULING_ABORT_ITEM = "abort_item"    # 放棄此工作項


@dataclass(frozen=True)
class L1Dispute:
    """一筆 L1 攔截爭議。immutable：裁決前不得被執行席修改。"""

    dispute_id: str
    run_id: str
    item_id: str
    l1_verdict: str           # REWORK（耗盡）或 ESCALATE
    l1_reason: str            # L1 攔截理由摘要
    executor_claim: str       # 執行席／指揮席的堅持主張
    failed_tests: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispute_id": self.dispute_id,
            "run_id": self.run_id,
            "item_id": self.item_id,
            "l1_verdict": self.l1_verdict,
            "l1_reason": self.l1_reason,
            "executor_claim": self.executor_claim,
            "failed_tests": list(self.failed_tests),
            "created_at": self.created_at,
        }


def _default_ruling_choices() -> list[EscalationChoice]:
    return [
        EscalationChoice(RULING_ACCEPT_L1, "接受 L1 攔截，重做／修正規格", "憲兵簽核即責任，預設採納"),
        EscalationChoice(RULING_LOWER_STANDARD, "L5 明示降低驗收標準", "留痕：由 L5 承擔品質責任"),
        EscalationChoice(RULING_ABORT_ITEM, "放棄此工作項", "止損，避免無限重做"),
    ]


def raise_l1_dispute(
    *,
    run_id: str,
    item_id: str,
    l1_verdict: str,
    l1_reason: str,
    executor_claim: str = "",
    failed_tests: tuple[str, ...] = (),
) -> L1Dispute:
    """建立爭議並寫入可觀測記錄（同步、不阻塞）。

    呼叫方（協調器）隨後應以 :func:`await_l5_ruling` 等待 L5 裁決。
    """
    dispute = L1Dispute(
        dispute_id=uuid.uuid4().hex[:12],
        run_id=run_id,
        item_id=item_id,
        l1_verdict=l1_verdict,
        l1_reason=l1_reason[:240],
        executor_claim=executor_claim[:240],
        failed_tests=tuple(failed_tests),
    )
    STORE.add_node(
        run_id,
        from_layer=int(RahoLayer.L1_INSPECTOR),
        to_layer=int(RahoLayer.L5_USER),
        kind=ARBITRATION_KIND,
        summary=f"L1 攔截爭議升級：{dispute.l1_reason}"[:240],
        status="blocked",
        payload=dispute.to_dict(),
    )
    return dispute


async def await_l5_ruling(
    dispute: L1Dispute,
    *,
    choices: list[EscalationChoice] | None = None,
    ttl: float | None = None,
    on_created: Any | None = None,
) -> dict[str, Any]:
    """等待 L5／人工裁決（逾時依 escalation 契約自動採第一案＝接受 L1）。

    回傳 ``{"action", "choice", "reply", ...}``；``choice`` 為 RULING_* 之一。
    """
    from backend.company.raho.escalation import wait_user_decision

    result = await wait_user_decision(
        run_id=dispute.run_id,
        item_id=dispute.item_id,
        question=(
            f"L1 憲兵攔截（{dispute.l1_verdict}）：{dispute.l1_reason}\n"
            f"執行席主張：{dispute.executor_claim or '（無）'}"
        ),
        choices=choices or _default_ruling_choices(),
        ttl=ttl,
        on_created=on_created,
    )
    apply_ruling(dispute, result)
    return result


def apply_ruling(dispute: L1Dispute, ruling: dict[str, Any]) -> dict[str, Any]:
    """把 L5 裁決寫成可觀測節點（L5 → L1/L2），回傳裁決摘要。"""
    choice = str(ruling.get("choice") or RULING_ACCEPT_L1)
    STORE.add_node(
        dispute.run_id,
        from_layer=int(RahoLayer.L5_USER),
        to_layer=int(RahoLayer.L1_INSPECTOR),
        kind=f"{ARBITRATION_KIND}_ruling",
        summary=f"L5 裁決：{choice}——{ruling.get('reply') or ''!s}"[:240],
        status="resolved",
        payload={"dispute_id": dispute.dispute_id, "choice": choice},
    )
    return {"dispute_id": dispute.dispute_id, "choice": choice, "ruling": dict(ruling)}


def resolve_l1_dispute(
    *,
    run_id: str,
    item_id: str,
    l1_verdict: str,
    l1_reason: str,
    executor_claim: str = "",
    failed_tests: tuple[str, ...] = (),
) -> dict[str, Any]:
    """同步路徑（非 async 調用方）：立即建檔並以逾時 0 自動裁決（＝接受 L1）。

    契約：同步路徑**不存在**「執行席勝訴」分支——預設接受 L1 攔截，
    要推翻只能走 async 路徑由 L5／人工明示。
    """
    dispute = raise_l1_dispute(
        run_id=run_id,
        item_id=item_id,
        l1_verdict=l1_verdict,
        l1_reason=l1_reason,
        executor_claim=executor_claim,
        failed_tests=failed_tests,
    )
    ruling = {
        "action": "auto",
        "choice": RULING_ACCEPT_L1,
        "reply": "同步路徑預設接受 L1 攔截；推翻須經 L5／人工顯式裁決",
        "timeout": True,
    }
    return apply_ruling(dispute, ruling)
