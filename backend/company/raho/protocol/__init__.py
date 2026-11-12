"""RAHO 協議（Role-Aware Hierarchical Orchestration）。

定義層級（RahoLayer）、車道與鏈、角色→層級映射、開關旗標、文字標籤、
身份／邊建構與質詢／升級／語意鎖資料模型。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- layers：RahoLayer、車道／鏈常數、層級說明與角色映射資料
- labels：車道／層級／方向／種類文字標籤與取用函式
- roles：角色 id 正規化與層級推導
- flags：環境變數開關、鎖定門檻與決策 TTL
- models：質詢題目／問題、升級選項、語意鎖與 MGP 前置提示詞
- edges：raho_identity、邊標註、目錄／圖與上級層級
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from backend.company.state import RoleType

from .edges import (
    GRILL_EDGES,
    annotate_edge,
    attach_raho_fields,
    grill_edges,
    raho_directory,
    raho_graph,
    raho_identity,
    superior_layer,
)
from .flags import (
    decision_ttl_seconds,
    l0_enabled,
    lock_threshold,
    mgp_enabled,
    raho_enabled,
    user_grill_enabled,
)
from .labels import (
    DIRECTION_GLYPH,
    DIRECTION_LABELS,
    KIND_LABELS,
    LANE_LABELS,
    LAYER_LABELS,
    LAYER_SHORT,
    direction_label,
    kind_label,
    lane_label,
    layer_label,
)
from .layers import (
    AUDITOR_DIM_THRESHOLD,
    CHOICE_MARK,
    CLEAR_MARK,
    COMMAND_CHAIN,
    ESCALATE_MARK,
    GRILL_MARK,
    INSPECT_CHAIN,
    KERNEL_CHAIN,
    LANE_COMMAND,
    LANE_INSPECT,
    LANE_KERNEL,
    LANE_LAYERS,
    LANE_ORDER,
    LAYER_META,
    LOCK_THRESHOLD,
    MAX_PHASE_ROUNDS,
    MAX_SUPERIOR_ROUNDS,
    MAX_USER_GRILL_TURNS,
    RAHO_CHAIN,
    RAHO_SPINE_ROLES,
    ROLE_ID_TO_LAYER,
    RahoLayer,
)
from .models import (
    MGP_EXECUTOR_PREAMBLE,
    MGP_SUPERIOR_PREAMBLE,
    EscalationChoice,
    GrillIssue,
    GrillQuestion,
    SemanticLock,
)
from .roles import canonical_role_id, role_to_raho_layer

__all__ = [
    "AUDITOR_DIM_THRESHOLD",
    "CHOICE_MARK",
    "CLEAR_MARK",
    "COMMAND_CHAIN",
    "DIRECTION_GLYPH",
    "DIRECTION_LABELS",
    "ESCALATE_MARK",
    "GRILL_EDGES",
    "GRILL_MARK",
    "INSPECT_CHAIN",
    "KERNEL_CHAIN",
    "KIND_LABELS",
    "LANE_COMMAND",
    "LANE_INSPECT",
    "LANE_KERNEL",
    "LANE_LABELS",
    "LANE_LAYERS",
    "LANE_ORDER",
    "LAYER_LABELS",
    "LAYER_META",
    "LAYER_SHORT",
    "LOCK_THRESHOLD",
    "MAX_PHASE_ROUNDS",
    "MAX_SUPERIOR_ROUNDS",
    "MAX_USER_GRILL_TURNS",
    "MGP_EXECUTOR_PREAMBLE",
    "MGP_SUPERIOR_PREAMBLE",
    "RAHO_CHAIN",
    "RAHO_SPINE_ROLES",
    "ROLE_ID_TO_LAYER",
    "Any",
    "EscalationChoice",
    "GrillIssue",
    "GrillQuestion",
    "IntEnum",
    "RahoLayer",
    "RoleType",
    "SemanticLock",
    "annotate_edge",
    "annotations",
    "attach_raho_fields",
    "canonical_role_id",
    "dataclass",
    "decision_ttl_seconds",
    "direction_label",
    "field",
    "grill_edges",
    "kind_label",
    "l0_enabled",
    "lane_label",
    "layer_label",
    "lock_threshold",
    "mgp_enabled",
    "os",
    "raho_directory",
    "raho_enabled",
    "raho_graph",
    "raho_identity",
    "role_to_raho_layer",
    "superior_layer",
    "user_grill_enabled",
]
