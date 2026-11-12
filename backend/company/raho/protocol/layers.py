"""RAHO 層級定義：RahoLayer、車道／鏈常數、層級說明與角色映射。"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

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
