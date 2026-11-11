"""執行流程 mixin（ExecutionMixin）：execute 主流程、執行-審查迴圈、MGP 裁決修補與作戰計畫建構。"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from backend.company.events import CompanyEvent
from backend.company.roles import RoleType
from backend.company.state import WorkItemStatus
from backend.company.work_item import WorkItemManager

from ._base import OrchestratorBase

logger = logging.getLogger(__name__)


class ExecutionMixin(OrchestratorBase):
    """execute 主流程、執行-審查迴圈、MGP 裁決修補與作戰計畫建構。"""

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

    # ═══════════════════════════════════════════════════════════
    # 階段 2：執行-審查迴圈
    # ═══════════════════════════════════════════════════════════

    async def _execute_review_loop(self, goal: str) -> None:
        """執行-審查主迴圈：平行執行就緒工作項（Semaphore 限制並行數），逐個審查。"""
        max_rounds = self.config.max_review_rounds

        while self.work_items.has_work_remaining():
            # 取消檢查點：每輪迴圈開始時
            if self._check_cancel():
                logger.info("執行迴圈偵測到取消請求，中止")
                return

            ready_items = self.work_items.get_ready_items()

            if not ready_items:
                # 檢查是否有阻塞的工作項
                blocked = self.work_items.get_blocked_by_deps()
                if blocked:
                    logger.warning(
                        "%d 個工作項因依賴未滿足而阻塞",
                        len(blocked),
                    )
                # 檢查是否全部完成
                if self.work_items.is_all_done():
                    break
                # 死鎖檢測：無就緒項、無執行中、無審查中項目時，
                # 剩餘工作項全部處於 blocked/rework 等無法推進狀態，
                # 繼續等待只會無限空轉 → 直接退出迴圈
                active_statuses = {
                    WorkItemStatus.EXECUTING,
                    WorkItemStatus.IN_REVIEW,
                    WorkItemStatus.REWORK,
                    WorkItemStatus.READY,
                }
                has_active = any(
                    item.status in active_statuses
                    for item in self.work_items.list_all()
                )
                if not has_active:
                    logger.warning(
                        "無可推進的工作項（全部阻塞或完成），退出執行迴圈"
                    )
                    break
                # 等待（實際場景中可能有非同步事件）
                await asyncio.sleep(0.1)
                continue

            # 自適應並發調整（優化 #6）
            self._adjust_concurrency()

            # 平行執行就緒工作項（Semaphore 限制並行數）
            self._log("parallel_execute", {
                "count": len(ready_items),
                "max_parallel": self._max_parallel,
            })
            tasks = [
                self._execute_with_semaphore(goal, item)
                for item in ready_items
            ]
            await asyncio.gather(*tasks)

            # 取消檢查點：gather 返回後立即早退，不再審查剛完成的項目
            if self._check_cancel():
                logger.info("執行迴圈偵測到取消請求（gather 後），中止")
                return

            # 審查每個剛完成的工作項
            for item in ready_items:
                # 重新取得最新狀態
                current = self.work_items.get(item.id)
                if current and current.status == WorkItemStatus.IN_REVIEW:
                    await self._review_item(goal, current, max_rounds)

    async def _execute_with_semaphore(self, goal: str, item) -> None:
        """用 Semaphore 包裝 _execute_single_item，限制並行數。"""
        async with self._worker_semaphore:
            await self._execute_single_item(goal, item)

    async def _maybe_resolve_mgp(
        self,
        goal: str,
        item,
        role_type: RoleType,
        raw: str,
        prompt: str,
        system_prompt: str,
        model: str,
        llm_opts: dict | None,
        timeout_s: float,
        seat: dict | None = None,
    ) -> tuple[str, str]:
        """若產出含 [GRILL]，走熱馬桶圈後重試一次執行。無標記則原樣返回。"""
        try:
            from backend.company.raho.escalation import resolve_grill
            from backend.company.raho.mgp import (
                parse_choices,
                parse_grill_output,
                strip_protocol_marks,
            )
            from backend.company.raho.protocol import mgp_enabled
        except Exception:
            return raw, prompt
        if not mgp_enabled():
            return raw, prompt
        kind, issues = parse_grill_output(raw)
        if kind == "clear":
            return raw, prompt
        extra_choices = parse_choices(raw) if kind == "escalate" else []
        self.events.emit(CompanyEvent.GRILL_RAISED, {
            "item_id": item.id,
            "title": item.title,
            "role": role_type.value,
            "issues": [i.to_dict() for i in issues],
        })
        resolved = await resolve_grill(
            run_id=self._run_id or item.id,
            item_id=item.id,
            goal=goal,
            title=item.title,
            description=item.description,
            issues=issues,
            assignee=role_type.value,
            choices=extra_choices or None,
            superior="manager",
            allowed_tools=self._allowed_tools_for(item),
            on_user_pending=lambda p: self._emit_user_pending(p, title=item.title),
        )
        self._apply_escalation_patch(item, resolved)
        reply = str(resolved.get("reply") or "").strip()
        self.events.emit(CompanyEvent.GRILL_RESOLVED, {
            "item_id": item.id,
            "layer": resolved.get("layer"),
            "action": resolved.get("action"),
            "timeout": bool(resolved.get("timeout")),
        })
        if resolved.get("timeout"):
            self.events.emit(CompanyEvent.RAHO_TIMEOUT, {
                "item_id": item.id, "choice": resolved.get("choice"),
            })
        if not reply:
            return strip_protocol_marks(raw) or raw, prompt
        next_prompt = prompt + f"\n\n【上級對質詢的裁決】\n{reply}\n請依裁決產出交付物，不要再重複質詢。"
        if isinstance(seat, dict):
            seat["context_sources"] = list(seat.get("context_sources") or []) + [{
                "kind": "grill_ruling",
                "label": f"產後質詢裁決（上級 layer={resolved.get('layer')}）",
                "text": reply,
            }]
        try:
            if timeout_s > 0:
                retried = await asyncio.wait_for(
                    self._execute_with_tool_loop(
                        next_prompt, system_prompt, model, role_type.value, item,
                        llm_kwargs=llm_opts, seat=seat,
                    ),
                    timeout=timeout_s,
                )
            else:
                retried = await self._execute_with_tool_loop(
                    next_prompt, system_prompt, model, role_type.value, item,
                    llm_kwargs=llm_opts, seat=seat,
                )
            kind2, _ = parse_grill_output(retried)
            if kind2 == "clear":
                return retried, next_prompt
            return strip_protocol_marks(retried) or reply, next_prompt
        except Exception as exc:
            logger.warning("MGP 重試執行失敗，使用裁決原文：%s", exc)
            return reply, next_prompt

    def _apply_escalation_patch(self, item, resolved: dict) -> None:
        """把 L3 SOP 重發的工具／預算寫回原子工作項。"""
        if not isinstance(resolved, dict) or not item:
            return
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        atomic = artifacts.get("atomic_role") if isinstance(artifacts.get("atomic_role"), dict) else {}
        tools = resolved.get("reissued_tools")
        if isinstance(tools, list) and tools:
            artifacts["allowed_tools"] = list(tools)
            if atomic:
                atomic["allowed_tools"] = list(tools)
                layer = atomic.get("task_layer")
                if isinstance(layer, dict):
                    layer["allowed_tools"] = list(tools)
        budget = resolved.get("reissued_budget")
        if isinstance(budget, dict):
            if budget.get("max_iterations") is not None:
                artifacts["max_iterations"] = budget["max_iterations"]
                if atomic:
                    atomic["max_iterations"] = budget["max_iterations"]
            if budget.get("token_budget") is not None:
                artifacts["token_budget"] = budget["token_budget"]
                if atomic:
                    atomic["token_budget"] = budget["token_budget"]

    def _build_from_battle_plan(self, plan: dict[str, Any]) -> list:
        """把 L3 作戰地圖孵化成工作項（含依賴與原子角色卡）。"""
        from backend.company.raho.atomic_pool import incubate_instance
        from backend.company.state import BudgetTier, WorkItemStatus

        template_role = {
            "web_scraper": RoleType.CRAWLER,
            "social_listener": RoleType.RESEARCHER,
            "pdf_extractor": RoleType.ANALYST,
            "data_synthesizer": RoleType.ANALYST,
            "swot": RoleType.ANALYST,
            "copy": RoleType.CONTENT_WRITER,
            "code": RoleType.DEVELOPER,
            "review": RoleType.REVIEWER,
            "plan": RoleType.COORDINATOR,
            "generic": RoleType.DEVELOPER,
            "research": RoleType.RESEARCHER,
            "file_ingest": RoleType.ANALYST,
        }
        available = {rt.value: rt for rt in self.config.roles}
        nodes = list(plan.get("dag_nodes") or [])
        instances = {
            str(row.get("node_id")): row
            for row in (plan.get("atomic_role_instances") or [])
            if isinstance(row, dict)
        }
        created: list[Any] = []
        id_map: dict[str, str] = {}
        for node in nodes:
            node_id = str(node.get("node_id") or f"N{len(created) + 1}")
            tmpl = str(node.get("assigned_role_template") or "generic")
            role = template_role.get(tmpl, RoleType.DEVELOPER)
            if role.value not in available:
                role = available.get("developer") or available.get("analyst") or next(iter(self.config.roles), RoleType.DEVELOPER)
            instance = instances.get(node_id) or {}
            desc = str(node.get("description") or "")
            item = self.work_items.create(
                title=desc[:80] or node_id,
                description=desc,
                assignee=role,
                created_by=RoleType.TACTICAL_COMMANDER,
                depends_on=[],
                tier=BudgetTier.SUMMARY if instance.get("token_budget", 3000) <= 2000 else BudgetTier.ROUTINE,
            )
            item.artifacts["node_id"] = node_id
            item.artifacts["battle_plan_id"] = plan.get("plan_id")
            incubate_instance(item, {**instance, "template_id": tmpl})
            item.transition_to(WorkItemStatus.READY)
            created.append(item)
            id_map[node_id] = item.id
        for node, item in zip(nodes, created):
            deps = [id_map[str(d)] for d in (node.get("depends_on") or []) if str(d) in id_map]
            item.depends_on = deps
        return created
