"""execute 主流程 mixin：公司目標執行入口。"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from backend.company.events import CompanyEvent
from backend.company.roles import RoleType
from backend.company.work_item import WorkItemManager

from .._base import OrchestratorBase

logger = logging.getLogger("backend.company.orchestrator.execution")


class _ExecutionRunMixin(OrchestratorBase):
    """公司目標 execute 主流程（初始化、拆分、執行、整合、定稿）。"""

    # ═══════════════════════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════════════════════

    async def execute(
        self,
        goal: str,
        ticket: dict[str, Any] | None = None,
        precomputed_planner: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """執行公司目標，回傳最終結果。

        這是主要的進入點，執行完整的公司運行流程。
        包含 Docker 容器預算管控：任務開始時記錄快照、
        預算緊張時自動建議優化。
        """
        if self.task_id:
            from backend.company.execution_gate import require_user_approved

            require_user_approved(self.task_id)
        self._run_log = []
        self._run_id = uuid.uuid4().hex
        # 綁定 run 上下文：decomposer／inspector 等 orchestrator 之外的席位
        # 投遞也能落到正確的 run 上（asyncio 每個任務各持一份上下文，互不污染）
        try:
            from backend.company.seat_io import bind_run

            bind_run(self._run_id, self.task_id)
        except Exception:
            logger.debug("席位 I/O run 綁定失敗（已忽略）", exc_info=True)
        self.budget.reset_task()
        self.work_items = WorkItemManager()
        self.decomposer.work_items = self.work_items

        # LLM 軌跡上下文：任務經理分析，再拆解、整合、終審
        from backend.core import llm_trace

        llm_trace.trace_phase.set("task_analysis")
        llm_trace.trace_role.set("manager")
        llm_trace.trace_item_id.set("")

        self._log(
            "company_start",
            {"goal": goal, "config": self.config.name},
            level=logging.INFO,
        )
        self.events.emit(CompanyEvent.COMPANY_START, {"goal": goal, "config": self.config.name})
        try:
            from backend.company.raho.protocol import raho_enabled
            from backend.company.raho.store import STORE as _RAHO_STORE

            if raho_enabled() and self._run_id:
                _RAHO_STORE.ensure_tree(self._run_id, goal)
        except Exception:
            pass

        # ── 階段 0：雲資源預算檢查（Docker + 阿里雲 BSS）──
        docker_snapshot = self.budget.record_docker_runtime()
        cloud_sync = self.budget.sync_cloud_from_billing()
        docker_ok, docker_reason = self._check_docker_budget()
        self._log("docker_budget_check", {
            "docker_cost": docker_snapshot["total_cost"],
            "aliyun_cost": cloud_sync.get("aliyun_usd", 0),
            "cloud_cost": cloud_sync.get("cloud_usd", 0),
            "api_cost": cloud_sync.get("api_usd", 0),
            "can_continue": docker_ok,
            "reason": docker_reason,
            "budget_pressure": round(self.budget.budget_pressure, 2),
        })

        # 預算緊張時，生成容器優化建議
        docker_suggestions = self.budget.get_docker_optimization_suggestions()
        docker_auto_optimized: dict[str, Any] = {"stopped": [], "failed": [], "saved_per_hour": 0.0}
        if docker_suggestions:
            high_priority = [s for s in docker_suggestions if s.get("priority") == "high"]
            if high_priority:
                # 預算壓力 >= 90%，自動停止非核心容器
                docker_auto_optimized = self._apply_docker_optimization(high_priority)
            self._log("docker_optimization", {
                "suggestions": [s["service"] for s in docker_suggestions],
                "auto_stopped": docker_auto_optimized["stopped"],
                "saved_per_hour": docker_auto_optimized["saved_per_hour"],
                "pressure": round(self.budget.budget_pressure, 2),
            }, degraded=True, level=logging.WARNING)

        if ticket or precomputed_planner:
            self._log(
                "command_chain_skipped",
                {"reason": "task_manager_analyzes"},
                level=logging.INFO,
            )

        # ── 任務經理分析並拆成工作項 ──
        self._log("phase", {"phase": "task_analysis", "module": "TaskManager"})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "task_analysis"})
        llm_trace.trace_phase.set("decompose")
        llm_trace.trace_role.set("manager")
        self._log("phase", {"phase": "decompose", "module": "TaskManager"})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "decompose"})
        decompose_result = await self.decomposer.decompose(goal)
        if not decompose_result.subtasks:
            return self._error_result("任務分解失敗，無法產生工作項")
        work_items = self.decomposer.build_work_items(
            decompose_result,
            created_by=RoleType.MANAGER,
        )
        decompose_meta = {
            "strategy": decompose_result.strategy.value,
            "execution_plan": decompose_result.execution_plan,
        }
        self._log(
            "task_analyzed",
            {
                "analyst": "manager",
                "subtask_count": len(work_items),
                "execution_plan": decompose_result.execution_plan,
            },
            level=logging.INFO,
        )
        self._log("decompose_done", {
            "subtask_count": len(work_items),
            "strategy": decompose_meta["strategy"],
            "execution_plan": decompose_meta["execution_plan"],
            "battle_plan_id": (self._battle_plan or {}).get("plan_id"),
        })
        self.events.emit(CompanyEvent.DECOMPOSE_DONE, {
            "subtask_count": len(work_items),
            "strategy": decompose_meta["strategy"],
            "execution_plan": decompose_meta["execution_plan"],
            "campaign": self._campaign,
            "battle_plan": self._battle_plan,
        })

        # ── 階段 2：執行-審查迴圈 ──
        llm_trace.trace_phase.set("execute_review")
        llm_trace.trace_role.set("")
        self._log("phase", {"phase": "execute_review", "work_items": len(work_items)})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "execute_review", "work_items": len(work_items)})
        await self._execute_review_loop(goal)

        # 取消檢查點：執行迴圈結束後
        if self._check_cancel():
            self._log("company_cancelled", {"at": "after_execute_review"}, level=logging.INFO)
            return self._error_result("任務已被使用者取消")

        # ── 階段 3：Synthesizer 整合（P1：可合併 Reviewer+Synthesizer）──
        llm_trace.trace_role.set("synthesizer")
        llm_trace.trace_item_id.set("")
        llm_trace.trace_phase.set("synthesize")
        self._log("phase", {"phase": "synthesize"})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "synthesize"})
        merge_enabled = os.getenv("EVOL_MERGE_REVIEW_SYNTH", "true").lower() == "true"
        if merge_enabled:
            final_output, merge_meta = await self._review_and_synthesize(goal)
            self._log("review_synth_merge", merge_meta)
        else:
            final_output = await self._synthesize(goal)
            merge_meta = {}

        # 取消檢查點：整合結束後
        if self._check_cancel():
            self._log("company_cancelled", {"at": "after_synthesize"}, level=logging.INFO)
            return self._error_result("任務已被使用者取消")

        # ── 階段 4：Manager 最終審查 ──
        llm_trace.trace_role.set("manager")
        llm_trace.trace_phase.set("final_review")
        self._log("phase", {"phase": "final_review"})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "final_review"})
        review_result = await self._manager_final_review(goal, final_output)

        # ── 階段 5：API＋雲資源成本結算（Docker + 阿里雲）──
        docker_final = self.budget.record_docker_runtime()
        cloud_final = self.budget.sync_cloud_from_billing()
        docker_delta = round(docker_final["total_cost"] - docker_snapshot["total_cost"], 4)

        self._log(
            "company_done",
            {
                "total_items": len(work_items),
                "completed_items": self.work_items.get_stats()["done"],
                "review_rounds": self._count_review_rounds(),
                "llm_cost": round(self.budget.task_api_spent, 4),
                "api_cost": round(self.budget.task_api_spent, 4),
                "docker_cost": self.budget.docker_cost,
                "aliyun_cost": self.budget.aliyun_cost,
                "cloud_cost": self.budget.cloud_cost,
                "docker_delta": docker_delta,
                "total_cost": round(self.budget.total_spent, 4),
                "cloud_sync": cloud_final,
            },
            level=logging.INFO,
        )
        self.events.emit(CompanyEvent.COMPANY_DONE, {
            "total_items": len(work_items),
            "completed_items": self.work_items.get_stats()["done"],
            "llm_cost": round(self.budget.task_api_spent, 4),
            "api_cost": round(self.budget.task_api_spent, 4),
            "docker_cost": self.budget.docker_cost,
            "aliyun_cost": self.budget.aliyun_cost,
            "cloud_cost": self.budget.cloud_cost,
            "total_cost": round(self.budget.total_spent, 4),
        })

        # ── 更新全局公司預算狀態（供 API 讀取）──
        try:
            from backend.services.company_budget import update_company_budget_state
            update_company_budget_state({
                "api_cost": self.budget.api_cost,
                "docker_cost": self.budget.docker_cost,
                "aliyun_cost": self.budget.aliyun_cost,
                "cloud_cost": self.budget.cloud_cost,
                "total_spent": self.budget.total_spent,
                "budget_pressure": self.budget.budget_pressure,
                "optimization_suggestions": docker_suggestions,
                "auto_optimized": docker_auto_optimized,
            })
        except ImportError:
            pass

        return {
            "success": True,
            "run_id": self._run_id,
            "goal": goal,
            "final_output": final_output,
            "review": review_result,
            "kanban": self.work_items.get_kanban(),
            "stats": self.work_items.get_stats(),
            "budget": self.budget.to_dict(),
            "docker": {
                "cost_snapshot_start": docker_snapshot["total_cost"],
                "cost_snapshot_end": docker_final["total_cost"],
                "cost_delta": docker_delta,
                "optimization_suggestions": docker_suggestions,
                "auto_optimized": docker_auto_optimized,
            },
            "run_log": self._run_log,
            "raho": self._raho_snapshot(),
            "campaign": self._campaign,
            "battle_plan": self._battle_plan,
            "commander": self._commander,
        }
