"""Tactical Commander（L3 戰術指揮官）：把 L4 門票拆成原子級作戰地圖。

接收 L4 需求審計官的戰術指令 JSON，強制檢查後拆成 DAG，
並為每個節點孵化 <200 Token 的 L2 原子執行者。無法拆解時
回退 L4；硬限制內不可行則上交 L5。

LLM 一律經 `backend.core.llm.call_llm`。規則引擎可單獨測試。

本檔案已於第五輪重構拆為套件：對外仍以
from backend.services.commander import TacticalCommander, plan_from_ticket 等名稱匯入；
實作分散在 prompts／templates／ticket／rules／grill／planner／plan／commander 等模組，行為不變。
"""

from __future__ import annotations

import logging

from backend.company.raho.protocol import GRILL_MARK, MGP_EXECUTOR_PREAMBLE

from .commander import TacticalCommander, apply_commander_system, l2_brief_ok
from .grill import (
    classify_grill,
    fill_allowed_tools,
    grill_rounds,
    increment_grill_round,
    infer_tools_from_text,
    respond_to_grill,
)
from .plan import battle_plan_to_yaml, build_escalation, plan_from_ticket
from .planner import l2_task_brief
from .prompts import (
    GRILL_CLARIFY,
    GRILL_DATA,
    GRILL_LOGIC,
    GRILL_SOP,
    GRILL_TOOL,
    STATUS_ESCALATE_USER,
    STATUS_PLAN_READY,
    STATUS_REJECT_L4,
    SYSTEM_PROMPT,
)
from .rules import (
    KNOWN_TOOLS,
    MAX_L2_PROMPT_TOKENS,
    clip_prompt,
    count_verbs,
    detect_infeasible,
    exclusions_ban_crawl,
    has_concrete_object,
    normalize_tools,
    pick_template,
    remap_template,
    serial_depth,
    validate_ticket,
)
from .ticket import estimate_tokens, extract_ticket, hours_until_deadline, ticket_hash

logger = logging.getLogger(__name__)

__all__ = [
    "GRILL_CLARIFY",
    "GRILL_DATA",
    "GRILL_LOGIC",
    "GRILL_MARK",
    "GRILL_SOP",
    "GRILL_TOOL",
    "KNOWN_TOOLS",
    "MAX_L2_PROMPT_TOKENS",
    "MGP_EXECUTOR_PREAMBLE",
    "STATUS_ESCALATE_USER",
    "STATUS_PLAN_READY",
    "STATUS_REJECT_L4",
    "SYSTEM_PROMPT",
    "TacticalCommander",
    "apply_commander_system",
    "battle_plan_to_yaml",
    "build_escalation",
    "classify_grill",
    "clip_prompt",
    "count_verbs",
    "detect_infeasible",
    "estimate_tokens",
    "exclusions_ban_crawl",
    "extract_ticket",
    "fill_allowed_tools",
    "grill_rounds",
    "has_concrete_object",
    "hours_until_deadline",
    "increment_grill_round",
    "infer_tools_from_text",
    "l2_brief_ok",
    "l2_task_brief",
    "normalize_tools",
    "pick_template",
    "plan_from_ticket",
    "remap_template",
    "respond_to_grill",
    "serial_depth",
    "ticket_hash",
    "validate_ticket",
]
