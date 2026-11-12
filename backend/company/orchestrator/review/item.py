"""Reviewer 審查 mixin：單一工作項審查與放行。"""

from __future__ import annotations

import logging
import time

from backend.company.budget import CostTracker
from backend.company.events import CompanyEvent
from backend.company.role_catalog import resolve_runtime
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.state import BudgetTier, WorkItemStatus
from backend.core.llm import llm_kwargs_for_role, parse_json_response

from .._base import OrchestratorBase, _llm_thread
from .._compat import call_llm

logger = logging.getLogger("backend.company.orchestrator.review")


class _ReviewItemMixin(OrchestratorBase):
    """單一工作項審查：Reviewer 檢視產出並在通過時放行。"""

    async def _review_item(self, goal: str, item, max_rounds: int) -> None:
        """L1 憲兵閘門 → Reviewer 審查工作項交付物。"""
        from backend.core import llm_trace

        llm_trace.trace_role.set("reviewer")
        llm_trace.trace_item_id.set(item.id)
        llm_trace.trace_phase.set("review")
        review_round = 0

        while review_round < max_rounds:
            review_round += 1
            current = self.work_items.get(item.id)
            if not current or current.status != WorkItemStatus.IN_REVIEW:
                break

            l1 = await self._run_l1_inspect(goal, current, review_round, max_rounds)
            if l1 is not None and getattr(l1, "verdict", "") == "REWORK":
                feedback = l1.details or "L1 憲兵退回重做"
                if l1.grill:
                    feedback = l1.grill.required_fix or l1.grill.details or feedback
                try:
                    from backend.company.raho.store import STORE as _RAHO_STORE

                    _RAHO_STORE.revoke_signed(current.id)
                except Exception:
                    pass
                current.artifacts["l1_signed"] = False
                self.work_items.request_rework(item.id, feedback)
                self._log("review_rework", {
                    "item_id": item.id, "round": review_round, "feedback": feedback[:200], "gate": "l1",
                })
                self.events.emit(CompanyEvent.REVIEW_REWORK, {
                    "item_id": item.id, "round": review_round, "feedback": feedback[:200], "gate": "l1",
                })
                await self._rework_item(goal, current, feedback)
                continue
            if l1 is not None and getattr(l1, "verdict", "") == "ESCALATE":
                feedback = l1.details or "L1 向上呈報"
                if l1.grill:
                    feedback = l1.grill.suggested_fix or l1.grill.details or feedback
                reply = ""
                esc = current.artifacts.get("l1_escalation") if isinstance(current.artifacts, dict) else {}
                if isinstance(esc, dict):
                    reply = str(esc.get("reply") or "")
                if reply:
                    self.work_items.request_rework(item.id, reply)
                    self.events.emit(CompanyEvent.REVIEW_REWORK, {
                        "item_id": item.id, "round": review_round, "feedback": reply[:200], "gate": "l1",
                    })
                    await self._rework_item(goal, current, reply)
                    continue
                self.work_items.block(item.id, feedback)
                self.events.emit(CompanyEvent.WORK_ITEM_ESCALATE, {
                    "item_id": item.id, "from": "l1", "to": "l3",
                })
                break

            role_def = self.config.roles.get(RoleType.REVIEWER, STANDARD_ROLES[RoleType.REVIEWER])
            model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
            runtime = resolve_runtime(RoleType.REVIEWER.value)
            if runtime.get("preferred_model"):
                model = runtime["preferred_model"]
            llm_opts = llm_kwargs_for_role(runtime)

            artifact_text = current.artifacts.get("output", str(current.artifacts))

            prompt = self.prompt_config.reviewer_review.format(
                goal=goal,
                title=current.title,
                description=current.description,
                artifact=artifact_text[:8000],  # 限制長度
            )

            system_prompt = (
                runtime.get("system_prompt")
                or role_def.system_prompt
                or self.prompt_config.reviewer_system
            )
            try:
                from backend.company.skills import inject_skills

                system_prompt = inject_skills(system_prompt, RoleType.REVIEWER.value)
            except Exception:
                pass
            _review_start = time.monotonic()
            try:
                raw = await _llm_thread(
                    call_llm,
                    prompt,
                    system=system_prompt,
                    model=model,
                    **llm_opts,
                )
                cost = CostTracker.estimate_cost_rough(model, "medium")
                self.budget.record_cost(cost, complexity="medium")
                current.actual_cost += cost
                self._record_seat_io(
                    self._seat_meta(
                        RoleType.REVIEWER, kind="review", phase="review",
                        role_label=role_def.name, attempt=review_round,
                    ),
                    current, RoleType.REVIEWER.value,
                    prompt=prompt, system=system_prompt, model=model, response=raw,
                    step=0, llm_kwargs=llm_opts,
                    duration_ms=(time.monotonic() - _review_start) * 1000.0,
                    cost_usd=cost, final=True,
                )

                result = parse_json_response(raw)

                if result.get("approved", False):
                    self.work_items.complete(item.id, {
                        "review_result": result,
                        "review_rounds": review_round,
                    })
                    self._log("review_approved", {
                        "item_id": item.id,
                        "rounds": review_round,
                        "score": result.get("score"),
                    })
                    self.events.emit(CompanyEvent.REVIEW_PASS, {
                        "item_id": item.id, "rounds": review_round, "score": result.get("score"),
                    })
                    break
                else:
                    feedback = result.get("feedback", "需修改")
                    self.work_items.request_rework(item.id, feedback)
                    self._log("review_rework", {
                        "item_id": item.id,
                        "round": review_round,
                        "feedback": feedback[:200],
                    })
                    self.events.emit(CompanyEvent.REVIEW_REWORK, {
                        "item_id": item.id, "round": review_round, "feedback": feedback[:200],
                    })

                    # 重新執行（Developer 根據回饋修改）
                    await self._rework_item(goal, current, feedback)

            except Exception as exc:
                logger.error("審查 %s 失敗：%s", item.id, exc)
                break

        # 達到最大輪數仍未通過 → 強制完成（附註未通過審查）
        current = self.work_items.get(item.id)
        if current and current.status != WorkItemStatus.DONE:
            # 若處於 EXECUTING 狀態，需先轉到 IN_REVIEW 再轉 DONE
            if current.status == WorkItemStatus.EXECUTING:
                self.work_items.transition(item.id, WorkItemStatus.IN_REVIEW)
            self.work_items.complete(item.id, {
                "force_completed": True,
                "reason": f"達到最大審查輪數 {max_rounds}",
            })
            self._log(
                "review_force_done",
                {
                    "item_id": item.id,
                    "max_rounds": max_rounds,
                    "reason": f"達到最大審查輪數 {max_rounds}，強制完成",
                },
                degraded=True,
                level=logging.INFO,
            )
            self.events.emit(CompanyEvent.REVIEW_FORCE_DONE, {
                "item_id": item.id, "max_rounds": max_rounds, "degraded": True,
            })
