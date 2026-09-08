"""遞歸對抗式分層組織（RAHO）—— EvoLoop 公司運行時進化層。

L0 環境與記憶核心（記憶／知識／態勢）滲透 L1–L5。
L5 用戶 Grill-Me → L4 需求審計官 → L3 戰術指揮官 → L2 原子執行者
L1 憲兵審查官獨立驗收：四維度壓力測試、雙向 Grill、簽核後才寫入共享記憶。
L2 執行前仍強制戰前檢查；無法決策則熱馬桶圈上交。
質詢樹與角色名冊共用 protocol.raho_identity。
"""

from backend.company.raho.atomic_executor import AtomicExecutorFactory
from backend.company.raho.blackboard import BlackboardEntry
from backend.company.raho.inspector import InspectorGate
from backend.company.raho.atomic_pool import assemble as assemble_atomic
from backend.company.raho.atomic_pool import incubate_instance
from backend.company.raho.atomic_pool import recycle as recycle_atomic
from backend.company.raho.commander import command_from_ticket, command_grill
from backend.company.raho.context_bus import downward_context, upward_brief
from backend.company.raho.planner import plan_campaign
from backend.company.raho.escalation import decide as decide_escalation
from backend.company.raho.escalation import resolve_grill
from backend.company.raho.grill_user import (
    grill_user_lock,
    grill_user_start,
    grill_user_status,
    grill_user_turn,
    should_grill_user,
)
from backend.company.raho.mgp import apply_mgp_system, parse_grill_output
from backend.company.raho.l0 import (
    brief_for as l0_brief_for,
    inject_l0,
    kernel_snapshot,
    remember_query,
)
from backend.company.raho.protocol import (
    LAYER_LABELS,
    RAHO_CHAIN,
    RahoLayer,
    attach_raho_fields,
    canonical_role_id,
    l0_enabled,
    raho_directory,
    raho_enabled,
    raho_identity,
    user_grill_enabled,
)
from backend.company.raho.scorecard import all_metrics, metrics_for, should_demote
from backend.company.raho.store import STORE

__all__ = [
    "STORE",
    "AtomicExecutorFactory",
    "BlackboardEntry",
    "InspectorGate",
    "LAYER_LABELS",
    "RAHO_CHAIN",
    "RahoLayer",
    "apply_mgp_system",
    "attach_raho_fields",
    "canonical_role_id",
    "inject_l0",
    "kernel_snapshot",
    "l0_brief_for",
    "l0_enabled",
    "raho_directory",
    "raho_identity",
    "remember_query",
    "assemble_atomic",
    "command_from_ticket",
    "command_grill",
    "decide_escalation",
    "incubate_instance",
    "downward_context",
    "grill_user_lock",
    "grill_user_start",
    "grill_user_status",
    "grill_user_turn",
    "metrics_for",
    "all_metrics",
    "parse_grill_output",
    "plan_campaign",
    "raho_enabled",
    "recycle_atomic",
    "resolve_grill",
    "should_demote",
    "should_grill_user",
    "upward_brief",
    "user_grill_enabled",
]
