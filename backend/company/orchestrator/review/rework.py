"""退回重做 mixin：依審查意見重跑角色並更新工作項。"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.company.budget import CostTracker
from backend.company.events import CompanyEvent
from backend.company.role_catalog import resolve_runtime
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.state import WorkItemStatus
from backend.core.llm import llm_kwargs_for_role, split_thinking

from .._base import OrchestratorBase
from .._compat import call_llm

logger = logging.getLogger("backend.company.orchestrator.review")


class _ReviewReworkMixin(OrchestratorBase):
    """退回重做：依審查意見重跑角色並更新工作項。"""

    async def _rework_item(self, goal: str, item, feedback: str) -> None:
        """讓 Developer 根據審查回饋修改交付物（含重試）。"""
        from backend.core import llm_trace

        self.work_items.transition(item.id, WorkItemStatus.EXECUTING)

        role_type = item.assignee or RoleType.DEVELOPER
        llm_trace.trace_role.set(role_type.value)
        llm_trace.trace_item_id.set(item.id)
        llm_trace.trace_phase.set("rework")
        role_def = self.config.roles.get(role_type)
        if role_def is None:
            role_def = STANDARD_ROLES.get(role_type, STANDARD_ROLES[RoleType.DEVELOPER])
        model = self.budget.resolve_model_for_tier(item.tier)
        runtime = resolve_runtime(role_type.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)

        context = self._build_context(item)

        prompt = f"""{self.prompt_config.developer_execute.format(
            goal=goal,
            role_name=role_def.name,
            title=item.title,
            description=item.description,
            context=context,
        )}

【審查回饋 - 請根據以下回饋修改】
{feedback}

請直接給出修改後的交付物："""

        rework_system = (
            runtime.get("system_prompt")
            or role_def.system_prompt
            or self.prompt_config.developer_execute_system
        )
        rework_seat = self._seat_meta(
            role_type, kind="rework", phase="rework", role_label=role_def.name
        )
        rework_seat["allowed_tools"] = self._allowed_tools_for(item) or []
        rework_seat["context_sources"] = [
            {"kind": "review_feedback", "label": "審查退回意見（重做依據）", "text": feedback},
            {"kind": "dependency", "label": "上游依賴產物（上下文匯流排）", "text": context},
        ]

        # ── 重試迴圈 ──
        retry_cfg = self.config.retry_config
        last_error = None

        for attempt in range(retry_cfg.max_retries + 1):
            rework_seat["attempt"] = attempt
            _rework_start = time.monotonic()
            try:
                if retry_cfg.deadline_seconds > 0:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(
                            call_llm,
                            prompt,
                            system=rework_system,
                            model=model,
                            **llm_opts,
                        ),
                        timeout=retry_cfg.deadline_seconds,
                    )
                else:
                    raw = await asyncio.to_thread(
                        call_llm,
                        prompt,
                        system=rework_system,
                        model=model,
                        **llm_opts,
                    )
                cost = CostTracker.estimate_cost_rough(model, "high")
                self.budget.record_cost(cost, complexity="high")
                item.actual_cost += cost
                self._record_seat_io(
                    rework_seat, item, role_type.value,
                    prompt=prompt, system=rework_system, model=model, response=raw,
                    step=0, llm_kwargs=llm_opts,
                    duration_ms=(time.monotonic() - _rework_start) * 1000.0,
                    cost_usd=cost, final=True,
                )

                thinking, visible = split_thinking(raw)
                item.artifacts["output"] = visible or raw
                if thinking:
                    item.artifacts["thinking"] = thinking
                self.work_items.request_review(item.id)

                self._log("rework_done", {
                    "item_id": item.id, "cost": round(cost, 4),
                })
                return

            except asyncio.TimeoutError:
                last_error = f"修改超時（{retry_cfg.deadline_seconds}s）"
            except Exception as exc:
                last_error = str(exc)
                logger.warning("修改 %s 失敗（attempt %d/%d）：%s", item.id, attempt + 1, retry_cfg.max_retries + 1, exc)

            if attempt < retry_cfg.max_retries:
                backoff = retry_cfg.retry_backoff_base * (2 ** attempt)
                self.events.emit(CompanyEvent.WORK_ITEM_RETRY, {
                    "item_id": item.id, "attempt": attempt + 1, "backoff": backoff,
                })
                await asyncio.sleep(backoff)

        # 最終失敗
        logger.error("修改 %s 最終失敗：%s", item.id, last_error)
        self.work_items.block(item.id, f"修改失敗：{last_error}")
