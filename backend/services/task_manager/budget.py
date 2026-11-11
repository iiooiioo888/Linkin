"""預算確認 mixin（BudgetMixin）：預算草案、批准／拒絕、分項回填、席位覆寫、現場寫入與敘事提交。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ._base import TaskManagerBase
from .models import TaskRecord

logger = logging.getLogger(__name__)


class BudgetMixin(TaskManagerBase):
    """預算草案、批准／拒絕、分項回填、席位覆寫、現場寫入與敘事提交。"""

    def start_budget_draft(self, record: TaskRecord) -> None:
        """只產生預算草案，不進入席位執行。"""
        record.resolved_path = "company"
        record.status = "awaiting_confirmation"
        record.phase = "budget_draft"
        self._persist(record)
        task = asyncio.create_task(self._draft_company_budget(record))
        self._running_tasks[record.task_id] = task

    async def _draft_company_budget(self, record: TaskRecord) -> None:
        from backend.company.execution_gate import auto_approve_enabled, compose_budget_draft

        draft_task = asyncio.current_task()
        try:
            if record.cancel_requested:
                return
            plan = await compose_budget_draft(record)
            record.budget_plan = plan
            self._add_event(record, "budget_draft_ready", {
                "feasibility": plan.get("feasibility"),
                "lines": len(plan.get("lines") or []),
            })
            if auto_approve_enabled():
                self.decide_budget(record.task_id, "approve", note="EVOL_BUDGET_AUTO_APPROVE")
                return
            record.status = "awaiting_confirmation"
            record.phase = "pending_user"
            self._add_event(record, "budget_confirmation_required", {"version": plan.get("version")})
            self._persist(record)
        except Exception as exc:
            logger.exception("預算草案失敗")
            record.budget_plan = {
                "status": "pending_user",
                "version": 1,
                "feasibility": "narrow",
                "execution_plan": "",
                "lines": [],
                "risks": [str(exc)],
                "assumptions": [],
                "confirmation": None,
                "ledger": {"reserved_credits": 0, "frozen": False},
                "note": str(exc),
            }
            record.status = "awaiting_confirmation"
            record.phase = "pending_user"
            record.error = ""
            self._persist(record)
        finally:
            running = self._running_tasks.get(record.task_id)
            if running is draft_task:
                self._running_tasks.pop(record.task_id, None)

    def decide_budget(self, task_id: str, action: str, note: str = "") -> tuple[bool, str]:
        """批准才凍結並下達。拒絕與逾時都不執行。"""
        from backend.company.execution_gate import expire_budget_if_needed

        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if expire_budget_if_needed(record):
            self._persist(record)
            return False, "預算確認已逾時，任務未執行"
        plan = record.budget_plan if isinstance(record.budget_plan, dict) else None
        if record.status in {"rejected", "expired", "cancelled", "completed", "failed"}:
            return False, f"任務已結束（{record.status}）"
        choice = (action or "").strip().lower()
        if choice == "reject":
            if plan is not None:
                plan["status"] = "rejected"
                plan["confirmation"] = {"action": "reject", "at": time.time(), "note": note}
            record.status = "rejected"
            record.phase = "rejected"
            record.error = note or "用戶拒絕預算方案，任務未執行"
            record.finished_at = time.time()
            running = self._running_tasks.get(task_id)
            if running is not None and not running.done():
                running.cancel()
            self._add_event(record, "budget_rejected", {"note": note})
            self._persist(record)
            return True, "已拒絕，不會執行"
        if choice != "approve":
            return False, "action 只能是 approve 或 reject"
        if not plan or plan.get("status") != "pending_user":
            return False, "預算草案尚未就緒"
        from backend.company.milestone_actions import commit_field_writes, create_confirmed_seats

        try:
            create_confirmed_seats(plan)
        except ValueError as exc:
            return False, str(exc)
        field_result = commit_field_writes(list(plan.get("field_writes") or []))
        plan["field_writes_result"] = field_result
        plan["status"] = "locked"
        plan["confirmation"] = {"action": "approve", "at": time.time(), "note": note}
        raw_ledger = plan.get("ledger")
        ledger: dict[str, Any] = dict(raw_ledger) if isinstance(raw_ledger, dict) else {}
        ledger["frozen"] = True
        plan["ledger"] = ledger
        record.budget_plan = plan
        record.phase = "approved"
        self._add_event(record, "budget_locked", {"version": plan.get("version")})
        self._reserve_execution_billing(record)
        record.status = "pending"
        self._persist(record)
        self.start_task(record)
        if field_result.get("status") == "blocked":
            return True, "已確認並下達。現場寫入未執行，任務維持開工"
        return True, "已確認並下達"

    def update_budget_lines(self, task_id: str, lines: list[dict[str, Any]]) -> tuple[bool, str]:
        from backend.company.execution_gate import expire_budget_if_needed, replace_budget_lines

        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if expire_budget_if_needed(record):
            self._persist(record)
            return False, "預算確認已逾時"
        plan = record.budget_plan if isinstance(record.budget_plan, dict) else None
        if not plan or plan.get("status") != "pending_user":
            return False, "目前不能回填分項"
        replace_budget_lines(plan, lines)
        self._add_event(record, "budget_lines_updated", {"version": plan.get("version")})
        self._persist(record)
        return True, "已更新分項"

    def update_confirmation_draft(
        self,
        task_id: str,
        *,
        new_seats: list[dict[str, Any]] | None = None,
        field_writes: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str]:
        """點頭前改新席位草稿與現場寫入。不寫目錄，不改世界觀。"""
        from backend.company.execution_gate import expire_budget_if_needed
        from backend.company.milestone_actions import replace_confirmation_draft

        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if expire_budget_if_needed(record):
            self._persist(record)
            return False, "確認已逾時"
        plan = record.budget_plan if isinstance(record.budget_plan, dict) else None
        if not plan or plan.get("status") != "pending_user":
            return False, "目前不能改確認內容"
        replace_confirmation_draft(plan, new_seats=new_seats, field_writes=field_writes)
        self._add_event(record, "confirmation_draft_updated", {"version": plan.get("version")})
        self._persist(record)
        return True, "已更新確認內容"

    def apply_seat_override(
        self,
        task_id: str,
        role_id: str,
        *,
        system_prompt: str | None = None,
        tools_allowed: list[str] | None = None,
    ) -> tuple[bool, str]:
        """已存在席位的提示詞與工具權限立刻寫進目錄。"""
        from backend.company.milestone_actions import apply_existing_override

        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        try:
            apply_existing_override(role_id, system_prompt=system_prompt, tools_allowed=tools_allowed)
        except KeyError as exc:
            return False, str(exc)
        except ValueError as exc:
            return False, str(exc)
        self._add_event(record, "seat_override_applied", {"role_id": role_id})
        self._persist(record)
        return True, "已寫入席位目錄"

    def retry_field_writes(self, task_id: str, writes: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
        """開工後若檢查沒過，可改數值再檢查。仍是整批通過才寫。"""
        from backend.company.milestone_actions import (
            commit_field_writes,
            replace_confirmation_draft,
        )

        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        plan = record.budget_plan if isinstance(record.budget_plan, dict) else None
        if not plan or plan.get("status") != "locked":
            return False, "任務尚未確認"
        if writes is not None:
            replace_confirmation_draft(plan, field_writes=writes)
        result = commit_field_writes(list(plan.get("field_writes") or []))
        plan["field_writes_result"] = result
        self._add_event(record, "field_writes_retried", {"status": result.get("status")})
        self._persist(record)
        if result.get("status") == "blocked":
            return True, "現場寫入未執行"
        return True, "現場寫入已通過檢查"

    def commit_narrative(self, task_id: str, kind: str, entity: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        from backend.company.milestone_actions import commit_narrative_entity

        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在", {}
        try:
            stored = commit_narrative_entity(kind, entity)
        except ValueError as exc:
            return False, str(exc), {}
        self._add_event(record, "narrative_committed", {"kind": stored.get("kind"), "id": (stored.get("entity") or {}).get("id")})
        self._persist(record)
        return True, "已寫入實體", stored

    def _reserve_execution_billing(self, record: TaskRecord) -> None:
        """批准後才預扣執行費。確認前的餘額預檢不走這裡。"""
        from backend.billing.context import billing_enabled, current_billing_user
        from backend.billing.task_lifecycle import begin_billed_task

        if (record.options or {}).get("billing"):
            return
        uid = record.user_id or current_billing_user()
        if not billing_enabled() or not uid:
            return
        meta = begin_billed_task(
            uid,
            task_id=record.task_id,
            baseline_tokens=max(500, len(record.query) // 2),
            model=str((record.options or {}).get("model") or "default"),
        )
        ledger = (record.budget_plan or {}).get("ledger")
        if isinstance(ledger, dict):
            ledger["reserved_credits"] = meta.get("reserved_credits") or 0
        record.options = {**(record.options or {}), "billing": meta}
