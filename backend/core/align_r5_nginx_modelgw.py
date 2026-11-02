"""Align R5：nginx /modelgw 暴露與雙電路共享邊界契約（shadow／紙面；非真改 nginx）。

紙面錨：Issue #148 talk §5；align-spec §10.1 R5；G-X1
（nginx ``/modelgw`` location 暴露、雙電路共享 — 與 Align **正交後置**）。

預設精神（契約／shadow only）：
- 請求暴露 ``/modelgw`` nginx location → 預設 **block**／``orthogonal_deferred``；
  shadow 記 ``would_expose``
- 請求雙電路共享 → **block**（對齊 L5 禁第三電路精神）；shadow 記
  ``would_share_dual_circuit``
- 僅文件／契約觀測、不觸碰實檔 → allow 只限「評估請求本身合法」，
  **永不**回傳「已改 nginx」
- fail-closed：缺明確 infra 授權旗標 → block

本模組只落地可測契約／枚舉／評估函式（含 shadow 風格記錄）。
**不**改 nginx／compose／入口路由實檔、**不**接雙電路、**不**改 WIRE／環境。
明示：``does_not_modify_nginx=True``、``does_not_wire_dual_circuit=True``、
``shadow_only=True``、``gx1_infra_separate_ticket=True``、
``ready_to_merge_product=False``、``wire_change="none"``、
``orthogonal_to_align=True``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)

# 契約識別（對 Analyst code-gap／docs 對表）
CONTRACT_ID = "ALIGN-R5"
CONTRACT_REFS = (
    "#148",
    "align-residual§5",
    "align-spec§10.1-R5",
    "G-X1",
)

# 明示旗標（契約 ≠ 真改 nginx／雙電路）
DOES_NOT_MODIFY_NGINX = True
DOES_NOT_WIRE_DUAL_CIRCUIT = True
SHADOW_ONLY = True
GX1_INFRA_SEPARATE_TICKET = True
ORTHOGONAL_TO_ALIGN = True
WIRE_CHANGE = "none"

# 允許的「僅觀測／文件」意圖（不觸碰實檔）
ALLOWED_INTENTS = frozenset({"docs_observe", "contract_eval"})
# 暴露／雙電路請求意圖（本波擋下；shadow 記 would_*）
BLOCKED_EXPOSE_INTENTS = frozenset({"expose_modelgw_location", "nginx_location_open"})
BLOCKED_DUAL_INTENTS = frozenset({"share_dual_circuit", "dual_circuit_merge"})


class R5Verdict(str, Enum):
    """R5 nginx／雙電路邊界評估結果。"""

    ALLOW = "allow"
    """僅文件／契約觀測：評估請求本身合法；不宣稱已改 nginx。"""

    BLOCK = "block"
    """缺 infra 授權／未知意圖等 fail-closed 擋下。"""

    ORTHOGONAL_DEFERRED = "orthogonal_deferred"
    """暴露 /modelgw location：與 Align 正交後置；shadow 記 would_expose。"""

    WOULD_SHARE_DUAL_CIRCUIT = "would_share_dual_circuit"
    """雙電路共享請求：契約擋下；shadow 記 would_share；未接線。"""


class R5BlockReason(str, Enum):
    """擋下理由。"""

    EXPOSE_MODELGW = "r5.expose_modelgw_orthogonal_deferred"
    DUAL_CIRCUIT = "r5.dual_circuit_share_blocked"
    MISSING_INFRA_AUTH = "r5.missing_infra_auth_fail_closed"
    UNKNOWN_INTENT = "r5.unknown_intent_blocked"
    NONE = "none"


class R5Intent(str, Enum):
    """請求意圖分類（契約面）。"""

    DOCS_OBSERVE = "docs_observe"
    CONTRACT_EVAL = "contract_eval"
    EXPOSE_MODELGW_LOCATION = "expose_modelgw_location"
    NGINX_LOCATION_OPEN = "nginx_location_open"
    SHARE_DUAL_CIRCUIT = "share_dual_circuit"
    DUAL_CIRCUIT_MERGE = "dual_circuit_merge"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class R5ModelgwIngressInput:
    """R5 nginx /modelgw 暴露與雙電路邊界評估輸入（非真改 nginx）。

    ``infra_auth_flag`` 必須為 True 才允許「評估請求本身」通過 allow 路徑；
    缺旗標 → fail-closed block（即使意圖為 docs_observe）。
    """

    intent: str = ""
    """意圖：``docs_observe``／``contract_eval``／``expose_modelgw_location``／
    ``nginx_location_open``／``share_dual_circuit``／``dual_circuit_merge``／空。"""

    infra_auth_flag: bool = False
    """明確 infra 授權旗標；缺則 fail-closed。"""

    would_expose_path: str | None = None
    """若走暴露請求，本會暴露的 path（僅 shadow 觀測；預設 /modelgw）。"""

    would_share_circuits: tuple[str, ...] | None = None
    """若走雙電路共享，本會合併的電路名（僅 shadow）。"""


@dataclass(frozen=True, slots=True)
class R5ModelgwIngressDecision:
    """Align R5 評估產出。"""

    verdict: R5Verdict = R5Verdict.BLOCK
    block_reason: R5BlockReason = R5BlockReason.NONE
    audit_event: str = "modelgw.r5.ingress.blocked"
    intent_normalized: str = "missing"

    # 恒假：本契約永不宣稱「已改 nginx」／「已接雙電路」
    nginx_modified: Literal[False] = False
    dual_circuit_wired: Literal[False] = False
    does_not_modify_nginx: Literal[True] = True
    does_not_wire_dual_circuit: Literal[True] = True
    shadow_only: Literal[True] = True
    orthogonal_to_align: Literal[True] = True
    wire_change: Literal["none"] = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "block_reason": self.block_reason.value,
            "audit_event": self.audit_event,
            "intent_normalized": self.intent_normalized,
            "nginx_modified": self.nginx_modified,
            "dual_circuit_wired": self.dual_circuit_wired,
            "does_not_modify_nginx": self.does_not_modify_nginx,
            "does_not_wire_dual_circuit": self.does_not_wire_dual_circuit,
            "shadow_only": self.shadow_only,
            "orthogonal_to_align": self.orthogonal_to_align,
            "wire_change": self.wire_change,
        }


@dataclass
class R5ShadowRecord:
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


def reset_r5_shadow_log() -> None:
    """測試用：清空 shadow 緩衝。"""
    _SHADOW_LOG.clear()


def r5_shadow_log() -> list[dict[str, Any]]:
    """回傳 shadow 記錄副本。"""
    return list(_SHADOW_LOG)


def record_r5_shadow(payload: dict[str, Any]) -> R5ShadowRecord:
    """記錄一筆 shadow 觀測（只記、不擋／不改閘／不改 WIRE）。"""
    rec = R5ShadowRecord(payload=dict(payload))
    as_dict = rec.to_dict()
    _SHADOW_LOG.append(as_dict)
    logger.info(
        "ALIGN-R5 shadow contract=%s payload_keys=%s",
        CONTRACT_ID,
        sorted(payload.keys()),
    )
    return rec


def _normalize_intent(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return R5Intent.MISSING.value
    if (
        s in ALLOWED_INTENTS
        or s in BLOCKED_EXPOSE_INTENTS
        or s in BLOCKED_DUAL_INTENTS
    ):
        return s
    return R5Intent.UNKNOWN.value


def evaluate_r5_modelgw_ingress(
    inp: R5ModelgwIngressInput,
) -> R5ModelgwIngressDecision:
    """評估 nginx /modelgw 暴露與雙電路共享邊界（契約／shadow；永不真改）。

    順序：缺 infra 授權 fail-closed → 暴露意圖 → 雙電路意圖 →
    未知／缺意圖 → docs／契約觀測 allow。
    """
    intent = _normalize_intent(inp.intent)

    # 1) 缺明確 infra 授權旗標 → fail-closed（即使意圖為觀測）
    if not inp.infra_auth_flag:
        decision = R5ModelgwIngressDecision(
            verdict=R5Verdict.BLOCK,
            block_reason=R5BlockReason.MISSING_INFRA_AUTH,
            audit_event="modelgw.r5.ingress.missing_infra_auth",
            intent_normalized=intent,
            nginx_modified=False,
            dual_circuit_wired=False,
        )
    # 2) 暴露 /modelgw location → orthogonal_deferred；shadow would_expose
    elif intent in BLOCKED_EXPOSE_INTENTS:
        decision = R5ModelgwIngressDecision(
            verdict=R5Verdict.ORTHOGONAL_DEFERRED,
            block_reason=R5BlockReason.EXPOSE_MODELGW,
            audit_event="modelgw.r5.ingress.orthogonal_deferred",
            intent_normalized=intent,
            nginx_modified=False,
            dual_circuit_wired=False,
        )
    # 3) 雙電路共享 → would_share_dual_circuit block
    elif intent in BLOCKED_DUAL_INTENTS:
        decision = R5ModelgwIngressDecision(
            verdict=R5Verdict.WOULD_SHARE_DUAL_CIRCUIT,
            block_reason=R5BlockReason.DUAL_CIRCUIT,
            audit_event="modelgw.r5.ingress.would_share_dual_circuit",
            intent_normalized=intent,
            nginx_modified=False,
            dual_circuit_wired=False,
        )
    # 4) 缺意圖／未知 → block（不猜）
    elif intent in (R5Intent.MISSING.value, R5Intent.UNKNOWN.value):
        decision = R5ModelgwIngressDecision(
            verdict=R5Verdict.BLOCK,
            block_reason=R5BlockReason.UNKNOWN_INTENT,
            audit_event="modelgw.r5.ingress.unknown_intent",
            intent_normalized=intent,
            nginx_modified=False,
            dual_circuit_wired=False,
        )
    # 5) docs_observe／contract_eval → allow（僅評估合法；永不改 nginx）
    else:
        decision = R5ModelgwIngressDecision(
            verdict=R5Verdict.ALLOW,
            block_reason=R5BlockReason.NONE,
            audit_event="modelgw.r5.ingress.docs_observe_ok",
            intent_normalized=intent,
            nginx_modified=False,
            dual_circuit_wired=False,
        )

    # shadow：附帶 would_expose／would_share 觀測（不寫環境）
    shadow_payload = decision.to_dict()
    if inp.would_expose_path is not None:
        shadow_payload["would_expose"] = inp.would_expose_path
    elif intent in BLOCKED_EXPOSE_INTENTS:
        shadow_payload["would_expose"] = "/modelgw"
    if inp.would_share_circuits is not None:
        shadow_payload["would_share_dual_circuit"] = list(inp.would_share_circuits)
    elif intent in BLOCKED_DUAL_INTENTS:
        shadow_payload["would_share_dual_circuit"] = True
    record_r5_shadow(shadow_payload)
    return decision


def contract_r5_flags() -> dict[str, Any]:
    """明示本波＝nginx／雙電路正交後置契約／shadow；非真改 nginx、非合並產品。"""
    return {
        "contract_id": CONTRACT_ID,
        "refs": list(CONTRACT_REFS),
        "does_not_modify_nginx": DOES_NOT_MODIFY_NGINX,
        "does_not_wire_dual_circuit": DOES_NOT_WIRE_DUAL_CIRCUIT,
        "shadow_only": SHADOW_ONLY,
        "gx1_infra_separate_ticket": GX1_INFRA_SEPARATE_TICKET,
        "ready_to_merge_product": False,
        "wire_change": WIRE_CHANGE,
        "orthogonal_to_align": ORTHOGONAL_TO_ALIGN,
        "does_not_claim_nginx_changed": True,
        "allowed_intents": sorted(ALLOWED_INTENTS),
        "blocked_expose_intents": sorted(BLOCKED_EXPOSE_INTENTS),
        "blocked_dual_intents": sorted(BLOCKED_DUAL_INTENTS),
        "note": (
            "Align R5＝nginx /modelgw 暴露與雙電路共享邊界契約（shadow only）；"
            "暴露→orthogonal_deferred；雙電路→block；只允許 docs_observe／"
            "contract_eval；不改 nginx／compose、不接雙電路、不改 WIRE；"
            "永不宣稱已改 nginx；G-X1 基礎設施另票"
        ),
    }


__all__ = [
    "ALLOWED_INTENTS",
    "BLOCKED_DUAL_INTENTS",
    "BLOCKED_EXPOSE_INTENTS",
    "CONTRACT_ID",
    "CONTRACT_REFS",
    "DOES_NOT_MODIFY_NGINX",
    "DOES_NOT_WIRE_DUAL_CIRCUIT",
    "GX1_INFRA_SEPARATE_TICKET",
    "ORTHOGONAL_TO_ALIGN",
    "SHADOW_ONLY",
    "WIRE_CHANGE",
    "R5BlockReason",
    "R5Intent",
    "R5ModelgwIngressDecision",
    "R5ModelgwIngressInput",
    "R5ShadowRecord",
    "R5Verdict",
    "contract_r5_flags",
    "evaluate_r5_modelgw_ingress",
    "r5_shadow_log",
    "record_r5_shadow",
    "reset_r5_shadow_log",
]
