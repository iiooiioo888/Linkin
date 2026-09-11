"""RAHO 共用協議：層級、標記、設定與資料結構。

遞歸對抗式分層組織（Recursive Adversarial Hierarchical Organization）分三條線，
禁止把 L0–L5 畫成單一職級金字塔（L1 不隸屬 L2／L3）：

  指揮鏈（Command）：L5 用戶 → L4 需求審計官 → L3 戰術指揮官 → L2 原子執行者
  獨立審查（Inspect）：L2 提交產出 → L1 憲兵；L1 可 Grill L2（重做）或 L3（規劃）
  環境核心（Kernel）：L0 滲透 L1–L5，不參與質詢、不可被質詢

質詢／上呈（Grill / Escalate）：
  L4 → L5 需求審計
  L3 → L4 戰略不可行；逾時或基礎設施缺失才跳 L5
  L2 → L3 戰前質詢；3 輪無解跳 L4／L5
  L1 → L2 退回重做；L1 → L3 質疑規劃；標準爭議／最終裁定才上呈 L4／L5

組織職級（RoleDefinition.level 0–4，數字越小越高層）與質詢層（L0–L5）分開：
  脊柱角色以本檔 LAYER_META／GRILL_EDGES 為準，禁止面板另寫一套名稱。
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
    """RAHO 質詢層（數字越大越高）。舊別名僅供相容，新程式請用右側正規名。"""

    L0_KERNEL = 0
    L1_INSPECTOR = 1
    L1_GRILL = 1  # 相容別名 → L1_INSPECTOR
    L2_EXECUTOR = 2
    L3_COMMANDER = 3
    L3_DECOMPOSER = 3  # 相容別名 → L3_COMMANDER
    L4_AUDITOR = 4
    L4_PLANNER = 4  # 相容別名 → L4_AUDITOR（戰役譯製仍是 L4 職能）
    L5_USER = 5


# ── 三條線（指揮／審查／核心），不是單一職級金字塔 ──

LANE_COMMAND = "command"
LANE_INSPECT = "inspect"
LANE_KERNEL = "kernel"
LANE_ORDER: tuple[str, ...] = (LANE_KERNEL, LANE_COMMAND, LANE_INSPECT)
LANE_LABELS: dict[str, str] = {
    LANE_KERNEL: "環境核心",
    LANE_COMMAND: "指揮鏈",
    LANE_INSPECT: "獨立審查",
}
COMMAND_CHAIN: tuple[int, ...] = (5, 4, 3, 2)
INSPECT_CHAIN: tuple[int, ...] = (1,)
KERNEL_CHAIN: tuple[int, ...] = (0,)
LANE_LAYERS: dict[str, tuple[int, ...]] = {
    LANE_KERNEL: KERNEL_CHAIN,
    LANE_COMMAND: COMMAND_CHAIN,
    LANE_INSPECT: INSPECT_CHAIN,
}

# ── 層級／角色統一身分（質詢樹、名冊、工作台共用）──

LAYER_META: dict[int, dict[str, Any]] = {
    0: {
        "layer": 0,
        "id": "l0_kernel",
        "role_id": "environment_kernel",
        "title": "環境與記憶核心",
        "short": "L0 核心",
        "full": "L0 環境與記憶核心",
        "lane": LANE_KERNEL,
        "reports_to": None,
        "grill_targets": [],
        "escalate_targets": [],
        "submit_targets": [],
        "independent": True,
    },
    1: {
        "layer": 1,
        "id": "l1_inspector",
        "role_id": "constitutional_inspector",
        "title": "憲兵審查官",
        "short": "L1 憲兵",
        "full": "L1 憲兵審查官",
        "lane": LANE_INSPECT,
        "reports_to": None,
        "grill_targets": ["atomic_executor", "tactical_commander"],
        "escalate_targets": ["requirement_auditor", "user"],
        "submit_targets": [],
        "independent": True,
    },
    2: {
        "layer": 2,
        "id": "l2_executor",
        "role_id": "atomic_executor",
        "title": "原子執行者",
        "short": "L2 執行",
        "full": "L2 原子執行者",
        "lane": LANE_COMMAND,
        "reports_to": "tactical_commander",
        "grill_targets": ["tactical_commander"],
        "escalate_targets": ["tactical_commander", "requirement_auditor", "user"],
        "submit_targets": ["constitutional_inspector"],
        "independent": False,
    },
    3: {
        "layer": 3,
        "id": "l3_commander",
        "role_id": "tactical_commander",
        "title": "戰術指揮官",
        "short": "L3 指揮",
        "full": "L3 戰術指揮官",
        "lane": LANE_COMMAND,
        "reports_to": "requirement_auditor",
        "grill_targets": ["requirement_auditor"],
        "escalate_targets": ["requirement_auditor", "user"],
        "submit_targets": ["atomic_executor"],
        "independent": False,
    },
    4: {
        "layer": 4,
        "id": "l4_auditor",
        "role_id": "requirement_auditor",
        "title": "需求審計官",
        "short": "L4 審計",
        "full": "L4 需求審計官",
        "lane": LANE_COMMAND,
        "reports_to": "user",
        "grill_targets": ["user"],
        "escalate_targets": ["user"],
        "submit_targets": ["tactical_commander"],
        "independent": False,
    },
    5: {
        "layer": 5,
        "id": "l5_user",
        "role_id": "user",
        "title": "用戶",
        "short": "L5 用戶",
        "full": "L5 用戶",
        "lane": LANE_COMMAND,
        "reports_to": None,
        "grill_targets": [],
        "escalate_targets": [],
        "submit_targets": ["requirement_auditor"],
        "independent": True,
    },
}

LAYER_LABELS: dict[int, str] = {layer: meta["full"] for layer, meta in LAYER_META.items()}
LAYER_SHORT: dict[int, str] = {layer: meta["short"] for layer, meta in LAYER_META.items()}

RAHO_SPINE_ROLES: frozenset[str] = frozenset(
    {
        "environment_kernel",
        "constitutional_inspector",
        "atomic_executor",
        "tactical_commander",
        "requirement_auditor",
        "user",
    }
)

RAHO_CHAIN: tuple[int, ...] = (5, 4, 3, 2, 1, 0)
ROLE_ID_TO_LAYER: dict[str, int] = {
    str(meta["role_id"]): int(layer) for layer, meta in LAYER_META.items()
}


def _full_for_role_id(role_id: str) -> str:
    layer = ROLE_ID_TO_LAYER.get(role_id)
    if layer is None:
        return role_id
    return str(LAYER_META[layer]["full"])


def _labels_for_ids(role_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    return [_full_for_role_id(rid) for rid in (role_ids or [])]


DIRECTION_LABELS: dict[str, str] = {
    "up": "質詢上拋",
    "down": "任務下達",
    "inspect": "獨立審查",
    "inject": "環境注入",
}
DIRECTION_GLYPH: dict[str, str] = {
    "up": "↑",
    "down": "↓",
    "inspect": "⇄",
    "inject": "⇢",
}


def _make_edge(
    from_layer: int,
    to_layer: int,
    kind: str,
    label: str,
    direction: str,
) -> dict[str, Any]:
    src = LAYER_META[from_layer]
    dst = LAYER_META[to_layer]
    return {
        "from_layer": from_layer,
        "to_layer": to_layer,
        "from_role": src["role_id"],
        "to_role": dst["role_id"],
        "from_label": src["full"],
        "to_label": dst["full"],
        "kind": kind,
        "label": label,
        "direction": direction,
        "lane": src.get("lane") if direction == "inject" else (
            LANE_INSPECT if direction == "inspect" else LANE_COMMAND
        ),
    }


# 正規邊。up=質詢上級；down=指揮下達；inspect=L1 雙向審查；inject=L0 滲透。
GRILL_EDGES: tuple[dict[str, Any], ...] = (
    _make_edge(5, 4, "mandate", "提交需求", "down"),
    _make_edge(4, 3, "campaign", "戰術指令下達", "down"),
    _make_edge(3, 2, "campaign", "孵化原子任務", "down"),
    _make_edge(2, 1, "submit", "提交產出驗收", "inspect"),
    _make_edge(4, 5, "user_grill", "需求審計", "up"),
    _make_edge(3, 4, "escalate", "戰略不可行", "up"),
    _make_edge(3, 5, "escalate", "基礎設施缺失", "up"),
    _make_edge(2, 3, "mgp", "戰前質詢", "up"),
    _make_edge(2, 4, "escalate", "戰前逾時跳級", "up"),
    _make_edge(1, 2, "rework", "退回重做", "inspect"),
    _make_edge(1, 3, "inspect", "質疑規劃", "inspect"),
    _make_edge(1, 4, "escalate", "標準爭議", "up"),
    _make_edge(1, 5, "escalate", "最終裁定", "up"),
    _make_edge(0, 4, "l0", "滲透決策層", "inject"),
    _make_edge(0, 3, "l0", "滲透規劃層", "inject"),
    _make_edge(0, 2, "l0", "滲透執行層", "inject"),
    _make_edge(0, 1, "l0", "滲透審查層", "inject"),
)

KIND_LABELS: dict[str, str] = {
    "mandate": "需求下達",
    "user_grill": "用戶審計",
    "mgp": "戰前質詢",
    "escalate": "向上呈報",
    "resolve": "解除阻塞",
    "timeout": "決策逾時",
    "user_decide": "用戶裁決",
    "inspect": "憲兵審查",
    "submit": "提交驗收",
    "campaign": "戰役下達",
    "rework": "退回重做",
    "l0": "環境注入",
    "memory": "記憶回放",
    "knowledge": "知識引用",
}

_ROLE_OVERLAYS: dict[str, dict[str, Any]] = {
    "environment_kernel": {"layer": 0, "title": "環境與記憶核心", "spine": True},
    "constitutional_inspector": {"layer": 1, "title": "憲兵審查官", "spine": True},
    "atomic_executor": {"layer": 2, "title": "原子執行者", "spine": True},
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


def l0_enabled() -> bool:
    return raho_enabled() and os.getenv("EVOL_RAHO_L0", "true").lower() in {
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
    """將現有 RoleType 映射到 RAHO 質詢層。"""
    value = _role_value(role)
    if not value:
        return RahoLayer.L2_EXECUTOR
    if value in ROLE_ID_TO_LAYER:
        return RahoLayer(ROLE_ID_TO_LAYER[value])
    overlay = _ROLE_OVERLAYS.get(value)
    if overlay:
        return RahoLayer(int(overlay["layer"]))
    if value.endswith("_lead") or value in {"architect", "coordinator"}:
        return RahoLayer.L3_COMMANDER
    return RahoLayer.L2_EXECUTOR


def canonical_role_id(layer: int | RahoLayer | None) -> str:
    """層級在質詢樹／名冊上的正規角色 id。"""
    try:
        key = int(layer) if layer is not None else 2
    except (TypeError, ValueError):
        key = 2
    return str(LAYER_META.get(key, LAYER_META[2]).get("role_id") or "")


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


def direction_label(direction: str | None) -> str:
    key = str(direction or "").strip()
    return DIRECTION_LABELS.get(key, key or "質詢")


def lane_label(lane: str | None) -> str:
    key = str(lane or "").strip()
    return LANE_LABELS.get(key, key or "指揮鏈")


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
    role_id = value or str(meta["role_id"] or "atomic_executor")
    spine = bool(overlay["spine"]) if overlay else role_id in RAHO_SPINE_ROLES
    full = f"L{resolved} {title}"
    grill_targets = list(meta.get("grill_targets") or [])
    escalate_targets = list(meta.get("escalate_targets") or [])
    submit_targets = list(meta.get("submit_targets") or [])
    lane = str(meta.get("lane") or LANE_COMMAND)
    return {
        "layer": resolved,
        "role_id": role_id,
        "title": title,
        "short": f"L{resolved} {title[:2]}" if overlay and not spine else str(meta["short"]),
        "full": full,
        "spine": spine,
        "lane": lane,
        "lane_label": lane_label(lane),
        "independent": bool(meta.get("independent")),
        "reports_to": meta.get("reports_to"),
        "grill_targets": grill_targets,
        "grill_target_labels": _labels_for_ids(grill_targets),
        "escalate_targets": escalate_targets,
        "escalate_target_labels": _labels_for_ids(escalate_targets),
        "submit_targets": submit_targets,
        "submit_target_labels": _labels_for_ids(submit_targets),
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
    snapshot["raho_lane"] = ident["lane"]
    snapshot["raho_lane_label"] = ident["lane_label"]
    snapshot["grill_targets"] = ident["grill_targets"]
    snapshot["grill_target_labels"] = ident["grill_target_labels"]
    snapshot["reports_to"] = ident["reports_to"]
    snapshot["escalate_targets"] = ident["escalate_targets"]
    snapshot["escalate_target_labels"] = ident["escalate_target_labels"]
    snapshot["submit_targets"] = ident["submit_targets"]
    snapshot["submit_target_labels"] = ident["submit_target_labels"]
    snapshot["raho_independent"] = ident["independent"]
    return snapshot


def _decorate_layer(meta: dict[str, Any]) -> dict[str, Any]:
    row = dict(meta)
    row["lane_label"] = lane_label(row.get("lane"))
    row["grill_target_labels"] = _labels_for_ids(row.get("grill_targets"))
    row["escalate_target_labels"] = _labels_for_ids(row.get("escalate_targets"))
    row["submit_target_labels"] = _labels_for_ids(row.get("submit_targets"))
    return row


def raho_directory(*, include_kernel: bool = True) -> list[dict[str, Any]]:
    layers = (0, 1, 2, 3, 4, 5) if include_kernel else (1, 2, 3, 4, 5)
    return [_decorate_layer(LAYER_META[layer]) for layer in layers if layer in LAYER_META]


def grill_edges(*, include_inject: bool = True) -> list[dict[str, Any]]:
    edges = [dict(edge) for edge in GRILL_EDGES]
    if include_inject:
        return edges
    return [edge for edge in edges if edge.get("direction") != "inject"]


def raho_graph() -> dict[str, Any]:
    """質詢樹／名冊共用的完整圖：三條線、層級、邊。"""
    return {
        "chain": list(RAHO_CHAIN),
        "command_chain": list(COMMAND_CHAIN),
        "inspect_chain": list(INSPECT_CHAIN),
        "kernel_chain": list(KERNEL_CHAIN),
        "lanes": {
            key: {"id": key, "label": LANE_LABELS[key], "layers": list(layers)}
            for key, layers in LANE_LAYERS.items()
        },
        "layers": raho_directory(),
        "edges": grill_edges(),
        "kind_labels": dict(KIND_LABELS),
        "direction_labels": dict(DIRECTION_LABELS),
        "lane_labels": dict(LANE_LABELS),
    }


def superior_layer(layer: RahoLayer) -> RahoLayer:
    """質詢上拋的預設下一層。L1 跳過執行層直上 L4；L0 不參與質詢。"""
    if layer == RahoLayer.L0_KERNEL:
        return RahoLayer.L0_KERNEL
    if layer == RahoLayer.L1_INSPECTOR:
        return RahoLayer.L4_AUDITOR
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
    choices: list[dict[str, str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": self.question,
            "why": self.why,
            "dimension": self.dimension,
        }
        if self.choices:
            payload["choices"] = self.choices
        return payload


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
