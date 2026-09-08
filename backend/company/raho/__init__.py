"""遞歸對抗式分層組織（RAHO）—— EvoLoop 公司運行時進化層。

L5 用戶 Grill-Me → L4 元規劃 DAG → L3 原子拆解 → L2 專注執行
L1 憲兵審查官獨立驗收：四維度壓力測試、雙向 Grill、簽核後才寫入共享記憶。
L2 執行前仍強制戰前檢查；無法決策則熱馬桶圈上交。
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
from backend.company.raho.protocol import (
    RahoLayer,
    raho_enabled,
    user_grill_enabled,
)
from backend.company.raho.scorecard import all_metrics, metrics_for, should_demote
from backend.company.raho.store import STORE

__all__ = [
    "STORE",
    "AtomicExecutorFactory",
    "BlackboardEntry",
    "InspectorGate",
    "RahoLayer",
    "apply_mgp_system",
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
