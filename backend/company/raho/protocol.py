"""RAHO 共用協議：層級、標記、設定與資料結構。

遞歸對抗式分層組織（Recursive Adversarial Hierarchical Organization）：
  L5 用戶 → L4 需求審計官 → L3 戰術指揮官 → L2 原子執行者 → L1 憲兵審查官
  L1 為獨立審查閘門：四維度驗收、雙向 Grill（L2 重做／L3 改指令），簽核後才寫入共享記憶。

質詢樹與角色名冊共用本檔的層級／角色身分，禁止前端或面板另寫一套 L1–L5 名稱。
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
    """RAHO 金字塔層級（數字越大越高）。舊別名保留給既有呼叫。"""

    L1_INSPECTOR = 1
    L1_GRILL = 1
    L2_EXECUTOR = 2
    L3_COMMANDER = 3
    L3_DECOMPOSER = 3
    L4_AUDITOR = 4
    L4_PLANNER = 4
    L5_USER = 5


# ── 層級／角色統一身分（質詢樹、名冊、工作台共用）──

LAYER_META: dict[int, dict[str, Any]] = {
    1: {
        "layer": 1,
        "id": "l1_inspector",
        "role_id": "constitutional_inspector",
        "title": "憲兵審查官",
        "short": "L1 憲兵",
        "full": "L1 憲兵審查官",
        "grill_targets": ["L2 原子執行者", "L3 戰術指揮官"],
    },
    2: {
        "layer": 2,
        "id": "l2_executor",
        "role_id": "",
        "title": "原子執行者",
        "short": "L2 執行",
        "full": "L2 原子執行者",
        "grill_targets": ["L3 戰術指揮官"],
    },
    3: {
        "layer": 3,
        "id": "l3_commander",
        "role_id": "tactical_commander",
        "title": "戰術指揮官",
        "short": "L3 指揮",
        "full": "L3 戰術指揮官",
        "grill_targets": ["L4 需求審計官", "L5 用戶"],
    },
    4: {
        "layer": 4,
        "id": "l4_auditor",
        "role_id": "requirement_auditor",
        "title": "需求審計官",
        "short": "L4 審計",
        "full": "L4 需求審計官",
        "grill_targets": ["L5 用戶"],
    },
    5: {
        "layer": 5,
        "id": "l5_user",
        "role_id": "user",
        "title": "用戶",
        "short": "L5 用戶",
        "full": "L5 用戶",
        "grill_targets": [],
    },
}

LAYER_LABELS: dict[int, str] = {layer: meta["full"] for layer, meta in LAYER_META.items()}
LAYER_SHORT: dict[int, str] = {layer: meta["short"] for layer, meta in LAYER_META.items()}

RAHO_SPINE_ROLES: frozenset[str] = frozenset(
    {
        "constitutional_inspector",
        "tactical_commander",
        "requirement_auditor",
    }
)

KIND_LABELS: dict[str, str] = {
    "user_grill": "用戶審計",
    "mgp": "戰前質詢",
    "escalate": "向上呈報",
    "resolve": "解除阻塞",
    "timeout": "決策逾時",
    "user_decide": "用戶裁決",
    "inspect": "憲兵審查",
    "campaign": "戰役下達",
    "rework": "退回重做",
}

_ROLE_OVERLAYS: dict[str, dict[str, Any]] = {
    "constitutional_inspector": {"layer": 1, "title": "憲兵審查官", "spine": True},
    "requirement_auditor": {"layer": 4, "title": "需求審計官", "spine": True},
    "tactical_commander": {"layer": 3, "title": "戰術指揮官", "spine": True},
    "user": {"layer": 5, "title": "用戶", "spine": True},
    "manager": {"layer": 4, "title": "專案經理", "spine": False},
    "reviewer": {"layer": 1, "title": "審查者", "spine": False},
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


def _role_value(role: RoleType | str | None) -> str:
    if role is None:
        return ""
    if isinstance(role, RoleType):
        return role.value
    return str(role).strip()


def role_to_raho_layer(role: RoleType | str | None) -> RahoLayer:
    """將現有 RoleType 映射到 RAHO 層。"""
    value = _role_value(role)
    if not value:
        return RahoLayer.L2_EXECUTOR
    overlay = _ROLE_OVERLAYS.get(value)
    if overlay:
        return RahoLayer(int(overlay["layer"]))
    if value in {"manager", "requirement_auditor"}:
        return RahoLayer.L4_AUDITOR
    if value in {"reviewer", "constitutional_inspector"}:
        return RahoLayer.L1_INSPECTOR
    if value.endswith("_lead") or value in {
        "architect",
        "coordinator",
        "product_lead",
        "tech_lead",
        "tactical_commander",
    }:
        return RahoLayer.L3_COMMANDER
    return RahoLayer.L2_EXECUTOR


def layer_label(layer: int | RahoLayer | None, *, short: bool = False) -> str:
    try:
        key = int(layer) if layer is not None else 2
    except (TypeError, ValueError):
        key = 2
    table = LAYER_SHORT if short else LAYER_LABELS
    return table.get(key, f"L{key}")


def kind_label(kind: str | None) -> str:
    key = str(kind or "").strip()
    return KIND_LABELS.get(key, key or "質詢")


def raho_identity(
    role: RoleType | str | None = None,
    layer: int | RahoLayer | None = None,
) -> dict[str, Any]:
    """質詢樹節點與角色名冊的統一身分。"""
    value = _role_value(role)
    overlay = _ROLE_OVERLAYS.get(value)
    resolved = int(overlay["layer"]) if overlay else (
        int(layer) if layer is not None else int(role_to_raho_layer(value or None))
    )
    if resolved not in LAYER_META:
        resolved = int(RahoLayer.L2_EXECUTOR)
    meta = LAYER_META[resolved]
    title = str(overlay["title"]) if overlay else str(meta["title"])
    role_id = value or str(meta["role_id"] or "")
    spine = bool(overlay["spine"]) if overlay else role_id in RAHO_SPINE_ROLES
    full = f"L{resolved} {title}"
    return {
        "layer": resolved,
        "role_id": role_id,
        "title": title,
        "short": f"L{resolved} {title[:2]}" if overlay and not spine else str(meta["short"]),
        "full": full,
        "spine": spine,
        "grill_targets": list(meta["grill_targets"]),
    }


def annotate_edge(
    from_layer: int,
    to_layer: int,
    *,
    from_role: str = "",
    to_role: str = "",
) -> dict[str, str]:
    src = raho_identity(from_role or None, from_layer)
    dst = raho_identity(to_role or None, to_layer)
    return {
        "from_role": from_role or src["role_id"],
        "to_role": to_role or dst["role_id"],
        "from_label": src["full"],
        "to_label": dst["full"],
        "from_short": src["short"],
        "to_short": dst["short"],
    }


def attach_raho_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    """把 RAHO 身分寫進角色快照（名冊／工作台）。"""
    ident = raho_identity(snapshot.get("id"))
    name = str(snapshot.get("name") or "").strip()
    if name and not ident["spine"]:
        ident = {
            **ident,
            "title": name,
            "full": f"L{ident['layer']} {name}",
            "short": f"L{ident['layer']} {name[:4]}",
        }
    snapshot["raho_layer"] = ident["layer"]
    snapshot["raho_label"] = ident["full"]
    snapshot["raho_short"] = ident["short"]
    snapshot["raho_title"] = ident["title"]
    snapshot["raho_spine"] = ident["spine"]
    snapshot["grill_targets"] = ident["grill_targets"]
    return snapshot


def raho_directory() -> list[dict[str, Any]]:
    return [dict(LAYER_META[layer]) for layer in (1, 2, 3, 4, 5)]


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
