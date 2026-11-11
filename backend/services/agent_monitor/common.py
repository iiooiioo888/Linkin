"""角色監控共用常數與小工具：日誌、狀態集合、事件提示、時間與狀態 helper。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.company.run_log import DEFAULT_RUN_LOG_DIR
from backend.company.state import WorkItemStatus

# 沿用原單檔模組名稱，維持日誌通道不變
logger = logging.getLogger("backend.services.agent_monitor")


# 沿用原單檔模組名稱，維持日誌通道不變
logger = logging.getLogger("backend.services.agent_monitor")

MAX_RUN_FILES = 40
MAX_ITEMS_PER_ROLE = 80
MAX_EVENTS_PER_ROLE = 60

OPEN_STATUSES = frozenset(
    {
        WorkItemStatus.PLANNING.value,
        WorkItemStatus.READY.value,
        WorkItemStatus.EXECUTING.value,
        WorkItemStatus.IN_REVIEW.value,
        WorkItemStatus.REWORK.value,
        WorkItemStatus.BLOCKED.value,
    }
)

ROLE_EVENT_HINTS: dict[str, frozenset[str]] = {
    "manager": frozenset(
        {
            "company_start",
            "decompose_done",
            "final_review_done",
            "company_done",
            "budget_warning",
            "budget_degrade",
            "grill_raised",
            "grill_resolved",
            "user_decision_needed",
            "raho_timeout",
        }
    ),
    "reviewer": frozenset(
        {"review_pass", "review_rework", "review_force_done", "review_approved"}
    ),
    "synthesizer": frozenset({"synthesize_done"}),
    "hub_operator": frozenset({"budget_warning", "budget_degrade", "tool_call"}),
    "github_ops": frozenset({"tool_call", "tool_result"}),
    "requirement_auditor": frozenset({"user_grill", "auditor_start", "auditor_lock", "auditor_fail"}),
    "tactical_commander": frozenset(
        {"decompose_done", "grill_raised", "grill_resolved", "user_decision_needed", "raho_timeout"}
    ),
    "constitutional_inspector": frozenset(
        {"review_pass", "review_rework", "review_force_done", "review_approved", "inspect"}
    ),
    "atomic_executor": frozenset(
        {"work_item_retry", "work_item_escalate", "execute_done", "grill_raised"}
    ),
}

PHASE_ROLE: dict[str, str] = {
    "decompose": "manager",
    "final_review": "manager",
    "synthesize": "synthesizer",
}


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(0.95 * (len(ordered) - 1))))
    return round(ordered[idx], 1)


def _run_log_dir() -> Path:
    return Path(os.getenv("EVOL_COMPANY_RUN_LOG_DIR", str(DEFAULT_RUN_LOG_DIR)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_key(raw: Any) -> str:
    if hasattr(raw, "value"):
        return str(raw.value)
    text = str(raw or "").strip()
    return text or WorkItemStatus.PLANNING.value


def _role_id(raw: Any) -> str | None:
    if raw is None:
        return None
    if hasattr(raw, "value"):
        return str(raw.value)
    text = str(raw).strip()
    return text or None


def _empty_inbox() -> dict[str, int]:
    return {s.value: 0 for s in WorkItemStatus}
