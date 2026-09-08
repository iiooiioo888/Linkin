"""RAHO 共用協議：層級、標記、設定與資料結構。

遞歸對抗式分層組織（Recursive Adversarial Hierarchical Organization）：
  L5 用戶 → L4 元規劃官 → L3 戰術指揮官 → L2 原子執行者 → L1 憲兵審查官
  L1 為獨立審查閘門：四維度驗收、雙向 Grill（L2 重做／L3 改指令），簽核後才寫入共享記憶。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from backend.company.state import RoleType

# ── 強制質詢／上交標記 ──

GRILL_MARK = "[GRILL]"
ESCALATE_MARK = "[ESCALATE]"
CLEAR_MARK = "[CLEAR]"
CHOICE_MARK = "[ESCALATE_CHOICE]"

LOCK_THRESHOLD = 0.92
MAX_USER_GRILL_TURNS = 10
MAX_SUPERIOR_ROUNDS = 3
MAX_PHASE_ROUNDS = 3
AUDITOR_DIM_THRESHOLD = 90.0


class RahoLayer(IntEnum):
    """RAHO 金字塔層級（數字越大越高）。"""

    L1_GRILL = 1
    L2_EXECUTOR = 2
    L3_DECOMPOSER = 3
    L4_PLANNER = 4
    L5_USER = 5


LAYER_LABELS: dict[int, str] = {
    RahoLayer.L1_GRILL: "L1 憲兵審查",
    RahoLayer.L2_EXECUTOR: "L2 原子執行",
    RahoLayer.L3_DECOMPOSER: "L3 戰術指揮",
    RahoLayer.L4_PLANNER: "L4 需求審計／元規劃",
    RahoLayer.L5_USER: "L5 用戶",
}


def raho_enabled() -> bool:
    return os.getenv("EVOL_RAHO_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def user_grill_enabled() -> bool:
    return raho_enabled() and os.getenv("EVOL_RAHO_USER_GRILL", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def mgp_enabled() -> bool:
    return raho_enabled() and os.getenv("EVOL_RAHO_MGP", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def lock_threshold() -> float:
    try:
        return float(os.getenv("EVOL_RAHO_LOCK_THRESHOLD", str(LOCK_THRESHOLD)))
    except ValueError:
        return LOCK_THRESHOLD


def decision_ttl_seconds() -> float:
    """決策逾時（熱馬桶圈）。0 = 立即自動裁決，不阻塞。"""
    try:
        return max(0.0, float(os.getenv("EVOL_RAHO_DECISION_TTL", "60")))
    except ValueError:
        return 60.0


def role_to_raho_layer(role: RoleType | str | None) -> RahoLayer:
    """將現有 RoleType 映射到 RAHO 層。"""
    if role is None:
        return RahoLayer.L2_EXECUTOR
    value = role.value if isinstance(role, RoleType) else str(role)
    if value in {"manager", "requirement_auditor"}:
        return RahoLayer.L4_PLANNER
    if value in {"reviewer", "constitutional_inspector"}:
        return RahoLayer.L1_GRILL
    if value.endswith("_lead") or value in {
        "architect",
        "coordinator",
        "product_lead",
        "tech_lead",
        "tactical_commander",
    }:
        return RahoLayer.L3_DECOMPOSER
    return RahoLayer.L2_EXECUTOR


def superior_layer(layer: RahoLayer) -> RahoLayer:
    if layer >= RahoLayer.L5_USER:
        return RahoLayer.L5_USER
    return RahoLayer(int(layer) + 1)


MGP_EXECUTOR_PREAMBLE = (
    "【強制質詢協議 MGP】"
    "在執行任何操作前，你必須先對上級指令進行完整性與邏輯性審查。"
    "若發現缺失、矛盾、工具權限不符或輸出規格不足以決策，"
    f"必須先以 {GRILL_MARK} 提出質疑（每條一行），待上級回覆確認後方可執行。"
    "禁止盲目執行。若指令完整可執行，直接產出交付物"
    f"（可選於首行標 {CLEAR_MARK}）。"
    "執行中若遇非預期分支，暫停並以 "
    f"{ESCALATE_MARK} 或 {CHOICE_MARK} 上交 2~3 個方案（A/B/C），禁止自行亂選。"
)

MGP_SUPERIOR_PREAMBLE = (
    "【強制質詢協議 MGP｜上級】"
    f"當收到下層 {GRILL_MARK} 質詢時，你必須在 {MAX_SUPERIOR_ROUNDS} 輪內給出明確答覆。"
    f"若無法答覆，必須輸出 {ESCALATE_MARK} 並附上無法決策的原因與 2~3 個建議方案。"
)


@dataclass
class GrillQuestion:
    question: str
    why: str = ""
    dimension: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "why": self.why,
            "dimension": self.dimension,
        }


@dataclass
class GrillIssue:
    """L2 對 L3 指令的一條質詢。"""

    message: str
    kind: str = "gap"  # gap | contradiction | tool | spec | constraint
    field: str = ""
    blocker_type: str = ""
    suggested_fix: str = ""
    target: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {"message": self.message, "kind": self.kind, "field": self.field}
        if self.blocker_type:
            payload["blocker_type"] = self.blocker_type
        if self.suggested_fix:
            payload["suggested_fix"] = self.suggested_fix
        if self.target:
            payload["target"] = self.target
        return payload


@dataclass
class EscalationChoice:
    key: str
    label: str
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "rationale": self.rationale}


@dataclass
class SemanticLock:
    locked: bool
    confidence: float
    brief: str
    session_id: str = ""
    turns: int = 0
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "locked": self.locked,
            "confidence": round(self.confidence, 4),
            "locked_brief": self.brief,
            "session_id": self.session_id,
            "turns": self.turns,
            "gaps": self.gaps,
        }
