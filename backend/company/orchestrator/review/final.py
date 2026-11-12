"""整合與終審 mixin：Reviewer+Synthesizer 合併、單獨整合、Manager 最終審查。"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.company.budget import CostTracker
from backend.company.events import CompanyEvent
from backend.company.role_catalog import resolve_runtime
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.state import BudgetTier
from backend.core.llm import llm_kwargs_for_role, parse_json_response

from .._base import OrchestratorBase, _llm_thread
from .._compat import call_llm

logger = logging.getLogger("backend.company.orchestrator.review")


class _ReviewFinalMixin(OrchestratorBase):
    """整合與終審：Reviewer+Synthesizer 合併、單獨整合、Manager 最終審查。"""

    # ═══════════════════════════════════════════════════════════
    # 階段 3：Synthesizer 整合
    # ═══════════════════════════════════════════════════════════

    async def _review_and_synthesize(self, goal: str) -> tuple[str, dict[str, Any]]:
        """P1：Reviewer + Synthesizer 合併 — 單次 LLM 審查並整合交付物。"""
        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        synth_runtime = resolve_runtime(RoleType.SYNTHESIZER.value)
        if synth_runtime.get("preferred_model"):
            model = synth_runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(synth_runtime)
        artifacts_text = self._collect_artifacts()
        stats = self.work_items.get_stats()

        prompt = self.prompt_config.review_synth_merge.format(
            goal=goal,
            artifacts=artifacts_text,
            total_items=stats["total"],
            completed_items=stats["done"],
            review_rounds=self._count_review_rounds(),
        )

        synth_system = self.prompt_config.review_synth_merge_system
        merge_seat = self._seat_meta(
            RoleType.SYNTHESIZER, kind="synthesize", phase="synthesize",
            role_label="Reviewer＋Synthesizer 合併",
        )
        merge_seat["context_sources"] = [
            {
                "kind": "artifacts",
                "label": f"全數交付物（{stats['done']}/{stats['total']} 完成）",
                "text": artifacts_text,
            }
        ]
        _merge_start = time.monotonic()
        try:
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=synth_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost, complexity="high")
            self._record_seat_io(merge_seat, None, RoleType.SYNTHESIZER.value,
                                 prompt=prompt, system=synth_system, model=model, response=raw,
                                 step=0, llm_kwargs=llm_opts,
                                 duration_ms=(time.monotonic() - _merge_start) * 1000.0,
                                 cost_usd=cost, final=True)

            result = parse_json_response(raw)
            final_output = str(result.get("final_output") or raw)
            meta = {
                "merged": True,
                "quality_passed": result.get("quality_passed", True),
                "quality_score": result.get("quality_score"),
                "quality_notes": result.get("quality_notes", ""),
                "cost": round(cost, 4),
            }
            self._log("synthesize_done", meta)
            return final_output, meta

        except Exception as exc:
            logger.warning("Review+Synth 合併失敗，降級為獨立 Synthesizer：%s", exc)
            output = await self._synthesize(goal)
            return output, {"merged": False, "fallback": str(exc)}

    async def _synthesize(self, goal: str) -> str:
        """讓 Synthesizer 整合所有已完成工作項的交付物。"""
        role_def = self.config.roles.get(
            RoleType.SYNTHESIZER, STANDARD_ROLES[RoleType.SYNTHESIZER]
        )
        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        runtime = resolve_runtime(RoleType.SYNTHESIZER.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)

        artifacts_text = self._collect_artifacts()
        stats = self.work_items.get_stats()

        prompt = self.prompt_config.synthesizer_merge.format(
            goal=goal,
            artifacts=artifacts_text,
            total_items=stats["total"],
            completed_items=stats["done"],
            review_rounds=self._count_review_rounds(),
        )

        synth_system = (
            runtime.get("system_prompt")
            or role_def.system_prompt
            or self.prompt_config.synthesizer_system
        )
        synth_seat = self._seat_meta(
            RoleType.SYNTHESIZER, kind="synthesize", phase="synthesize", role_label=role_def.name
        )
        synth_seat["context_sources"] = [
            {
                "kind": "artifacts",
                "label": f"全數交付物（{stats['done']}/{stats['total']} 完成）",
                "text": artifacts_text,
            }
        ]
        _synth_start = time.monotonic()
        try:
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=synth_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost, complexity="high")
            self._record_seat_io(
                synth_seat, None, RoleType.SYNTHESIZER.value,
                prompt=prompt, system=synth_system, model=model, response=raw,
                step=0, llm_kwargs=llm_opts,
                duration_ms=(time.monotonic() - _synth_start) * 1000.0,
                cost_usd=cost, final=True,
            )

            self._log("synthesize_done", {"cost": round(cost, 4)})
            return raw

        except Exception as exc:
            logger.error("整合失敗：%s", exc)
            return self._collect_artifacts()  # 降級：直接拼接

    # ═══════════════════════════════════════════════════════════
    # 階段 4：Manager 最終審查
    # ═══════════════════════════════════════════════════════════

    async def _manager_final_review(self, goal: str, final_output: str) -> dict:
        """Manager 最終審查整合結果。"""
        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        runtime = resolve_runtime(RoleType.MANAGER.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)
        stats = self.work_items.get_stats()

        prompt = self.prompt_config.manager_final_review.format(
            goal=goal,
            final_output=final_output[:8000],
            total_items=stats["total"],
            review_rounds=self._count_review_rounds(),
            total_cost=round(self.budget.task_spent, 4),
        )

        manager_system = self.prompt_config.manager_decompose_system
        final_seat = self._seat_meta(
            RoleType.MANAGER, kind="final_review", phase="final_review",
            role_label=getattr(self.config, "name", "") or "Manager",
        )
        final_seat["context_sources"] = [
            {"kind": "deliverable", "label": "待終審的整合交付物", "text": final_output[:8000]},
            {
                "kind": "stats",
                "label": f"工作項 {stats['total']} / 審查輪數 {self._count_review_rounds()}"
                f" / 已花費 ${self.budget.task_spent:.4f}",
                "text": "",
            },
        ]
        _final_start = time.monotonic()
        try:
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=manager_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "medium")
            self.budget.record_cost(cost, complexity="medium")
            self._record_seat_io(
                final_seat, None, RoleType.MANAGER.value,
                prompt=prompt, system=manager_system, model=model, response=raw,
                step=0, llm_kwargs=llm_opts,
                duration_ms=(time.monotonic() - _final_start) * 1000.0,
                cost_usd=cost, final=True,
            )

            result = parse_json_response(raw)
            self._log("final_review_done", result)
            return result

        except Exception as exc:
            logger.error("最終審查失敗：%s", exc)
            # 降級路徑：審查異常時自動通過，但必須留下可追蹤的持久軌跡
            self._log(
                "final_review_degraded",
                {"error": str(exc), "approved": True, "summary": "自動通過"},
                degraded=True,
                level=logging.INFO,
            )
            self.events.emit(CompanyEvent.FINAL_REVIEW_DEGRADED, {
                "error": str(exc), "degraded": True,
            })
            return {"approved": True, "summary": "自動通過", "error": str(exc), "degraded": True}
