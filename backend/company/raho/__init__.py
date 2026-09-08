"""遞歸對抗式分層組織（RAHO）—— EvoLoop 公司運行時進化層。

L5 用戶 Grill-Me → L4 元規劃 DAG → L3 原子拆解 → L2 專注執行
L1 憲兵反射內建於每個 L2：執行前強制質詢，無法決策則熱馬桶圈上交。
"""

from backend.company.raho.atomic_pool import assemble as assemble_atomic
from backend.company.raho.atomic_pool import recycle as recycle_atomic
from backend.company.raho.context_bus import downward_context, upward_brief
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
from backend.company.raho.scorecard import all_metrics, metrics_for
from backend.company.raho.store import STORE

__all__ = [
    "STORE",
    "RahoLayer",
    "apply_mgp_system",
    "assemble_atomic",
    "decide_escalation",
    "downward_context",
    "grill_user_lock",
    "grill_user_start",
    "grill_user_status",
    "grill_user_turn",
    "metrics_for",
    "all_metrics",
    "parse_grill_output",
    "raho_enabled",
    "recycle_atomic",
    "resolve_grill",
    "should_grill_user",
    "upward_brief",
    "user_grill_enabled",
]
