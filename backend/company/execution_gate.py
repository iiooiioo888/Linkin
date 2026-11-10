"""公司任務開工閘門。

預算草案可以先做。席位執行、寫入型工具與執行費凍結必須等用戶確認把方案鎖上。
確認逾時或拒絕都不會自動開跑。只有顯式設定 EVOL_BUDGET_AUTO_APPROVE 才會跳過確認。
"""

from __future__ import annotations

import os
import time
from typing import Any

CONFIRM_TTL_SEC = float(os.getenv("EVOL_BUDGET_CONFIRM_TTL_SEC", "3600") or 0)


class ExecutionNotApproved(RuntimeError):
    """預算方案尚未鎖定，執行器必須拒絕。"""


def auto_approve_enabled() -> bool:
    return os.getenv("EVOL_BUDGET_AUTO_APPROVE", "").strip().lower() in {"1", "true", "on", "yes"}


def require_user_approved(task_id: str) -> None:
    """有任務編號時，方案狀態必須是 locked。沒有編號的單元測試不在這道閘門。"""
    if not (task_id or "").strip():
        return
    from backend.services.task_manager import task_manager

    record = task_manager.get_task(task_id, skip_tenant_check=True)
    plan = getattr(record, "budget_plan", None) if record is not None else None
    if not isinstance(plan, dict) or plan.get("status") != "locked":
        raise ExecutionNotApproved("預算方案尚未經用戶確認，不能下達執行")


def expire_budget_if_needed(record: Any) -> bool:
    """逾時改為 expired，不啟動執行。"""
    plan = getattr(record, "budget_plan", None)
    if not isinstance(plan, dict) or plan.get("status") != "pending_user":
        return False
    if record.status not in {"awaiting_confirmation", "pending"}:
        return False
    deadline = plan.get("deadline")
    if not deadline or time.time() <= float(deadline):
        return False
    plan["status"] = "expired"
    plan["confirmation"] = {
        "action": "expire",
        "at": time.time(),
        "note": "確認逾時，不執行",
    }
    record.status = "expired"
    record.phase = "expired"
    record.error = "預算確認逾時，任務未執行"
    record.finished_at = time.time()
    return True


def _lines_from_subtasks(subtasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for index, task in enumerate(subtasks):
        if not isinstance(task, dict):
            continue
        lines.append({
            "line_id": str(index),
            "title": str(task.get("title") or ""),
            "assignee": str(task.get("assignee") or ""),
            "subject": "unfilled",
            "quantity": None,
            "unit_price_usd": None,
            "amount_usd": None,
            "assumption": "未登記，待能力負責人回填",
            "confidence": "low",
            "phase": task.get("phase"),
            "complexity": task.get("complexity"),
            "depends_on": task.get("depends_on") or [],
        })
    return lines


async def compose_budget_draft(record: Any) -> dict[str, Any]:
    """組上下文包並請任務經理出草案。失敗也留下待確認方案，不直接執行。"""
    from backend.company.budget import BudgetManager
    from backend.company.decomposer import TaskDecomposer
    from backend.company.manager_briefing import assemble_manager_context
    from backend.company.roles import BUILTIN_TEMPLATES

    config = BUILTIN_TEMPLATES.get(getattr(record, "template", "") or "") or BUILTIN_TEMPLATES["quick_task"]
    budget = BudgetManager(config.budget)
    pack = assemble_manager_context(record.query, config, budget)
    subtasks: list[dict[str, Any]] = []
    plan_text = ""
    meta: dict[str, Any] = {}
    try:
        result = await TaskDecomposer(config, budget).decompose(record.query)
        subtasks = [item for item in result.subtasks if isinstance(item, dict)]
        plan_text = result.execution_plan or ""
        meta = dict(result.meta or {})
    except Exception as exc:
        meta = {"error": str(exc), "feasibility": "narrow"}
    now = time.time()
    plan = {
        "status": "pending_user",
        "version": 1,
        "feasibility": meta.get("feasibility") or ("go" if subtasks else "narrow"),
        "execution_plan": plan_text,
        "risks": meta.get("risks") or [],
        "assumptions": meta.get("assumptions") or [],
        "budget_draft": meta.get("budget_draft") if isinstance(meta.get("budget_draft"), dict) else {},
        "lines": _lines_from_subtasks(subtasks),
        "context_omitted": pack.get("omitted") or {},
        "context_excerpt": str(pack.get("text") or "")[:1200],
        "valid_roles": pack.get("valid_roles") or "",
        "confirmation": None,
        "ledger": {"reserved_credits": 0, "frozen": False},
        "created_at": now,
        "deadline": now + CONFIRM_TTL_SEC if CONFIRM_TTL_SEC > 0 else None,
        "note": str(meta.get("error") or ""),
    }
    from backend.company.milestone_actions import absorb_analysis

    return absorb_analysis(plan, meta)


def replace_budget_lines(plan: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    """負責人回填分項。單價仍可維持未登記。"""
    cleaned: list[dict[str, Any]] = []
    for index, raw in enumerate(lines):
        if not isinstance(raw, dict):
            continue
        cleaned.append({
            "line_id": str(raw.get("line_id") or index),
            "title": str(raw.get("title") or ""),
            "assignee": str(raw.get("assignee") or ""),
            "subject": str(raw.get("subject") or "unfilled"),
            "quantity": raw.get("quantity"),
            "unit_price_usd": raw.get("unit_price_usd"),
            "amount_usd": raw.get("amount_usd"),
            "assumption": str(raw.get("assumption") or "未登記"),
            "confidence": str(raw.get("confidence") or "low"),
            "phase": raw.get("phase"),
            "complexity": raw.get("complexity"),
            "depends_on": raw.get("depends_on") or [],
        })
    plan["lines"] = cleaned
    plan["version"] = int(plan.get("version") or 1) + 1
    return plan
