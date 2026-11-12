"""TaskDecomposer 的 LLM 拆分與階段抽取（call_llm 經 .._compat 解析套件層 patch）（自 decomposer/service.py 抽出）。"""

from __future__ import annotations

import time
from typing import Any

from backend.company.budget import CostTracker
from backend.company.state import BudgetTier, RoleType
from backend.core.llm import llm_kwargs_for_role, parse_json_response

from .._compat import call_llm
from ..llm import _llm_thread
from ..types import DecompositionResult, DecompositionStrategy, _draft_assumptions
from .state import logger
from .strategies import _StrategiesMixin


class _LlmMixin(_StrategiesMixin):

    # ═══════════════════════════════════════════════════════════
    # LLM 驅動拆分
    # ═══════════════════════════════════════════════════════════

    async def _llm_decompose(self, goal: str) -> DecompositionResult:
        """LLM 驅動拆分：利用 LLM 理解目標語義，智能分解。"""
        try:
            from backend.company.manager_briefing import assemble_manager_context

            context_pack = assemble_manager_context(goal, self.config, self.budget)
        except Exception:
            logger.debug("任務經理上下文包組裝失敗", exc_info=True)
            context_pack = {
                "text": "【任務】\n" + goal[:500] + "\n\n【約束】\n上下文包組裝失敗。不要假設未列出的資源、角色、技能或 MCP。",
                "valid_roles": "/".join(rt.value for rt in self.config.roles) or "developer",
                "omitted": {},
                "role_ids": [],
                "low_relevance": True,
            }
        valid_roles = str(context_pack.get("valid_roles") or "developer")

        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        llm_opts: dict = {}
        try:
            from backend.company.role_catalog import resolve_runtime

            runtime = resolve_runtime(RoleType.MANAGER.value)
            if runtime.get("preferred_model"):
                model = runtime["preferred_model"]
            llm_opts = llm_kwargs_for_role(runtime)
        except Exception:
            llm_opts = {}
        prompt = self.prompt_config.manager_decompose.format(
            context_pack=context_pack["text"],
            valid_roles=valid_roles,
            task_budget=self.config.budget.task_limit_usd,
            active_tier=round(self.budget.budget_pressure, 2),
        )
        try:
            from backend.company.raho.scorecard import planning_paradigm_hint

            hint = planning_paradigm_hint()
            if hint:
                prompt = prompt + "\n\n" + hint
        except Exception:
            pass

        _dec_start = time.monotonic()
        try:
            # 同步 LLM 呼叫必須離開 event loop：否則逾時重試期間整個服務
            # （含 /tasks/*/cancel）都會被凍結（2026-09-10 取消失靈根因）
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=self.prompt_config.manager_decompose_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost, complexity="high")
            try:
                from backend.company.raho.protocol import layer_label, role_to_raho_layer
                from backend.company.seat_io import record_seat_io

                _layer = int(role_to_raho_layer(RoleType.MANAGER))
                record_seat_io({
                    "item_id": "",
                    "title": goal[:80],
                    "role": RoleType.MANAGER.value,
                    "role_label": "Manager（任務分解）",
                    "layer": _layer,
                    "layer_label": layer_label(_layer),
                    "kind": "decompose",
                    "model": model or "",
                    "tier": BudgetTier.CRITICAL.value,
                    "system": self.prompt_config.manager_decompose_system,
                    "prompt": prompt,
                    "response": raw,
                    "duration_ms": round((time.monotonic() - _dec_start) * 1000.0, 1),
                    "cost_usd": round(cost, 6),
                    "context_sources": [
                        {
                            "kind": "context_pack",
                            "label": "任務經理上下文包",
                            "text": context_pack["text"][:4000],
                            "omitted": context_pack.get("omitted") or {},
                        },
                    ],
                })
            except Exception:
                logger.debug("分解席位投遞軌跡異常（已忽略）", exc_info=True)

            result = parse_json_response(raw)
            subtasks = result.get("subtasks", [])
            execution_plan = result.get("execution_plan", "")

            # 從 LLM 回傳的 phase 欄位提取階段資訊
            phases = self._extract_phases_from_subtasks(subtasks)

            return DecompositionResult(
                goal=goal,
                strategy=DecompositionStrategy.LLM,
                subtasks=subtasks,
                execution_plan=execution_plan,
                phases=phases,
                meta={
                    "model": model,
                    "cost": round(cost, 4),
                    "draft": True,
                    "feasibility": result.get("feasibility") or "",
                    "budget_draft": result.get("budget_draft") or {},
                    "risks": result.get("risks") or [],
                    "assumptions": _draft_assumptions(result),
                    "context_omitted": context_pack.get("omitted") or {},
                },
            )

        except Exception as exc:
            logger.error("LLM 拆分失敗，降級為 RULE 策略：%s", exc)
            return self._rule_decompose(goal)

    def _extract_phases_from_subtasks(
        self,
        subtasks: list[dict[str, Any]],
    ) -> list[list[int]]:
        """從 subtasks 的 phase 欄位提取階段分組。

        優先使用 LLM 標註的 phase，若無則使用依賴拓樸計算。
        """
        # 檢查是否所有 subtask 都有 phase 欄位
        has_phases = all(
            isinstance(t.get("phase"), (int, float))
            for t in subtasks
        )
        if has_phases:
            max_phase = max(int(t.get("phase", 1)) for t in subtasks)
            phases: list[list[int]] = [[] for _ in range(max_phase)]
            for i, t in enumerate(subtasks):
                p = int(t.get("phase", 1)) - 1
                phases[p].append(i)
            return [p for p in phases if p]

        # 回退到依賴拓樸計算
        return self.plan_parallel_execution(subtasks)
