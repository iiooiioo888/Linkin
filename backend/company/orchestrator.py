"""多代理人公司協調器。

將 EvoLoop 反思迴圈擴展為完整的公司運行時，協調多個 AI 角色
分工合作完成複雜目標。核心流程：

  1. TaskDecomposer 接收目標 → 分解為工作項（主功能模組）
  2. 工作項依賴解析 → 平行執行（Developer 角色）
  3. 每個工作項執行完 → Reviewer 審查
  4. 審查不通過 → 退回修改（最多 N 輪）
  5. 所有工作項完成 → Synthesizer 整合
  6. Manager 最終審查 → 產出最終交付物

全程內建預算追蹤與模型層級路由。

任務拆分（TaskDecomposer）已提升為獨立的一級模組，
可脫離 CompanyOrchestrator 單獨使用與測試。
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from backend.company.budget import BudgetManager, CostTracker
from backend.company.decomposer import (
    TaskDecomposer,
)
from backend.company.docker_tools import (
    DOCKER_TOOLS,
    can_use_docker_tool,
    execute_docker_tool,
)
from backend.company.tools import tool_registry
from backend.company.react_loop import ReActExecutor
from backend.company.role_memory import get_role_memory
from backend.company.events import CompanyEvent, EventBus
from backend.company.prompts import PromptConfig
from backend.company.role_catalog import resolve_runtime
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.run_log import append_run_record, utc_now_iso
from backend.company.state import (
    BudgetTier,
    CompanyConfig,
    CompanyRunState,
    WorkItemStatus,
)
from backend.company.work_item import WorkItemManager
from backend.core.llm import call_llm, llm_kwargs_for_role, parse_json_response, split_thinking
from backend.services.docker_manager import DockerManager, get_docker_manager

logger = logging.getLogger(__name__)


class CompanyOrchestrator:
    """公司協調器：管理多角色分工執行流程。

    任務拆分委派給 TaskDecomposer（獨立主功能模組）。
    """

    def __init__(
        self,
        config: CompanyConfig | None = None,
        decomposer: TaskDecomposer | None = None,
        prompt_config: PromptConfig | None = None,
        docker_manager: DockerManager | None = None,
    ):
        self.config = config or CompanyConfig(roles=STANDARD_ROLES)
        self.budget = BudgetManager(self.config.budget)
        self.work_items = WorkItemManager()
        self._run_state: CompanyRunState | None = None
        self._run_log: list[dict[str, Any]] = []
        self._run_id: str | None = None
        self.prompt_config = prompt_config or self.config.prompt_config
        self.events = EventBus()
        # EventBus 事件同步寫入持久軌跡 sink（JSONL）
        self.events.on(self._persist_bus_event)
        # 任務拆分器（可注入，方便測試）
        self.decomposer = decomposer or TaskDecomposer(
            self.config, self.budget, self.work_items
        )
        # 並行工作池信號量（優化 #6：自適應並發控制）
        self._max_parallel = self.config.max_parallel_workers
        self._worker_semaphore = asyncio.Semaphore(self._max_parallel)
        # 自適應並發控制狀態
        self._concurrency_stats: dict[str, Any] = {
            "success_times": [],  # 成功請求的響應時間
            "rate_limit_count": 0,  # 429 錯誤計數
            "last_adjustment": 0,  # 上次調整時間
        }
        # Docker 管理服務（可注入，方便測試；若為 None 則自動獲取）
        self.docker = docker_manager
        # 取消標誌：由外部（task_manager）設置，執行迴圈檢查此標誌
        self.cancel_requested = False
        self._campaign: dict[str, Any] = {}
        self._battle_plan: dict[str, Any] = {}
        self._commander: dict[str, Any] = {}

    def request_cancel(self) -> None:
        """請求取消公司任務（執行迴圈會在下一個檢查點中止）。"""
        self.cancel_requested = True
        logger.info("公司任務已請求取消（run_id=%s）", self._run_id)

    def _check_cancel(self) -> bool:
        """檢查是否已請求取消。"""
        return self.cancel_requested

    # ═══════════════════════════════════════════════════════════
    # 自適應並發控制（優化 #6）
    # ═══════════════════════════════════════════════════════════

    def _adjust_concurrency(self) -> None:
        """根據 API 響應時間和錯誤率動態調整並發數。"""
        import time as _time
        now = _time.monotonic()
        # 每 30 秒最多調整一次
        if now - self._concurrency_stats["last_adjustment"] < 30:
            return
        self._concurrency_stats["last_adjustment"] = now

        success_times = self._concurrency_stats["success_times"]
        rate_limit_count = self._concurrency_stats["rate_limit_count"]

        old_max = self._max_parallel

        # 有 429 錯誤 → 降低並發
        if rate_limit_count > 0:
            self._max_parallel = max(1, self._max_parallel - 1)
            logger.info(
                "自適應並發：檢測到 %d 次限流，並發數 %d → %d",
                rate_limit_count, old_max, self._max_parallel,
            )
            self._concurrency_stats["rate_limit_count"] = 0

        # 響應時間穩定且無錯誤 → 逐步提升
        elif len(success_times) >= 5:
            avg_time = sum(success_times[-10:]) / len(success_times[-10:])
            if avg_time < 5.0:  # 平均響應 < 5 秒
                self._max_parallel = min(
                    self.config.max_parallel_workers * 2,  # 不超過配置的 2 倍
                    self._max_parallel + 1,
                )
                if self._max_parallel != old_max:
                    logger.info(
                        "自適應並發：響應穩定（均 %.1fs），並發數 %d → %d",
                        avg_time, old_max, self._max_parallel,
                    )

        # 更新信號量（僅在增加時重建）
        if self._max_parallel != old_max:
            self._worker_semaphore = asyncio.Semaphore(self._max_parallel)

        # 清理舊的響應時間記錄
        if len(success_times) > 100:
            self._concurrency_stats["success_times"] = success_times[-50:]

    # ═══════════════════════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════════════════════

    async def execute(self, goal: str, ticket: dict[str, Any] | None = None) -> dict[str, Any]:
        """執行公司目標，回傳最終結果。

        這是主要的進入點，執行完整的公司運行流程。
        包含 Docker 容器預算管控：任務開始時記錄快照、
        預算緊張時自動建議優化。
        """
        self._run_log = []
        self._run_id = uuid.uuid4().hex
        self.budget.reset_task()
        self.work_items = WorkItemManager()
        self.decomposer.work_items = self.work_items

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
        except Exception:  # noqa: BLE001
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

        # ── 階段 1a：L4 元規劃官產出戰役 DAG ──
        self._log("phase", {"phase": "campaign_plan", "module": "RahoPlanner"})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "campaign_plan"})
        try:
            from backend.company.raho.planner import plan_campaign
            from backend.company.raho.protocol import RahoLayer, raho_enabled
            from backend.company.raho.store import STORE as _RAHO_STORE

            if raho_enabled():
                campaign = plan_campaign(goal)
                self._campaign = campaign.to_dict()
                if self._run_id:
                    _RAHO_STORE.set_campaign(self._run_id, self._campaign, goal)
                    _RAHO_STORE.add_node(
                        self._run_id,
                        from_layer=int(RahoLayer.L4_PLANNER),
                        to_layer=int(RahoLayer.L3_DECOMPOSER),
                        kind="campaign",
                        summary=campaign.brief(240),
                        status="resolved",
                        payload=self._campaign,
                        goal=goal,
                    )
                self.events.emit(CompanyEvent.CAMPAIGN_PLANNED, {
                    "node_count": len(campaign.nodes),
                    "source": campaign.source,
                    "campaign": self._campaign,
                })
                self._log("campaign_planned", {
                    "node_count": len(campaign.nodes),
                    "source": campaign.source,
                })
        except Exception:  # noqa: BLE001
            logger.debug("L4 戰役規劃略過", exc_info=True)

        # ── 階段 1b：L3 戰術指揮官把 L4 門票拆成原子作戰地圖 ──
        self._log("phase", {"phase": "decompose", "module": "TacticalCommander"})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "decompose"})
        work_items: list = []
        decompose_meta = {"strategy": "commander", "execution_plan": ""}
        try:
            from backend.company.raho.commander import command_from_ticket
            from backend.company.raho.protocol import raho_enabled
            from backend.services.commander import extract_ticket

            l4_ticket = ticket if isinstance(ticket, dict) else None
            if l4_ticket is None:
                l4_ticket = extract_ticket(goal)
            if raho_enabled() and l4_ticket:
                pack = command_from_ticket(l4_ticket)
                self._commander = pack
                if pack.get("status") == "REJECT_TO_L4":
                    defects = "；".join(pack.get("defects") or ["門票檢查未過"])
                    return {
                        **self._error_result(f"L3 退回 L4：{defects}"),
                        "status": "REJECT_TO_L4",
                        "commander": pack,
                    }
                if pack.get("status") == "ESCALATE_TO_USER":
                    return {
                        **self._error_result(f"L3 上交用戶：{pack.get('reason') or '不可行'}"),
                        "status": "ESCALATE_TO_USER",
                        "commander": pack,
                    }
                if pack.get("status") == "PLAN_READY" and pack.get("battle_plan"):
                    self._battle_plan = pack["battle_plan"]
                    work_items = self._build_from_battle_plan(self._battle_plan)
                    decompose_meta = {
                        "strategy": "commander",
                        "execution_plan": pack.get("battle_plan_yaml") or pack["battle_plan"].get("plan_id", ""),
                    }
                    settings = (self._battle_plan.get("global_settings") or {})
                    try:
                        workers = int(settings.get("max_parallel_workers") or 0)
                        if workers > 0:
                            self._max_parallel = workers
                            self._worker_semaphore = asyncio.Semaphore(workers)
                    except (TypeError, ValueError):
                        pass
                    self.events.emit(CompanyEvent.BATTLE_PLANNED, {
                        "plan_id": self._battle_plan.get("plan_id"),
                        "node_count": len(self._battle_plan.get("dag_nodes") or []),
                        "rush_mode": bool(pack.get("rush_mode")),
                    })
        except Exception:  # noqa: BLE001
            logger.debug("L3 戰術拆解略過，回退 TaskDecomposer", exc_info=True)

        if not work_items:
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
            try:
                from backend.company.raho.atomic_pool import assemble as assemble_atomic
                from backend.company.raho.protocol import raho_enabled

                if raho_enabled():
                    for _item in work_items:
                        assemble_atomic(_item)
            except Exception:  # noqa: BLE001
                logger.debug("原子角色組裝略過", exc_info=True)

        try:
            from backend.company.raho.protocol import raho_enabled

            if raho_enabled() and self._campaign:
                from backend.company.raho.planner import CampaignMap, tag_work_items

                tag_work_items(work_items, CampaignMap.from_dict(self._campaign, goal))
        except Exception:  # noqa: BLE001
            logger.debug("戰役節點掛載略過", exc_info=True)
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
        self._log("phase", {"phase": "execute_review", "work_items": len(work_items)})
        self.events.emit(CompanyEvent.PHASE_CHANGE, {"phase": "execute_review", "work_items": len(work_items)})
        await self._execute_review_loop(goal)

        # 取消檢查點：執行迴圈結束後
        if self._check_cancel():
            self._log("company_cancelled", {"at": "after_execute_review"}, level=logging.INFO)
            return self._error_result("任務已被使用者取消")

        # ── 階段 3：Synthesizer 整合（P1：可合併 Reviewer+Synthesizer）──
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
            from backend.main import update_company_budget_state
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

    def get_kanban(self) -> dict:
        """取得當前看板狀態。"""
        return self.work_items.get_kanban()

    def get_budget_status(self) -> dict:
        """取得預算狀態。"""
        return self.budget.to_dict()

    def _raho_snapshot(self) -> dict[str, Any]:
        try:
            from backend.company.raho.store import STORE

            run_id = self._run_id or ""
            tree = STORE.get_tree(run_id)
            pending = [p.to_dict() for p in STORE.list_pending(run_id)]
            return {
                "run_id": run_id,
                "tree": tree.to_dict() if tree else None,
                "pending_decisions": pending,
                "campaign": self._campaign or (tree.campaign if tree else {}),
                "battle_plan": self._battle_plan,
                "commander": self._commander,
            }
        except Exception:  # noqa: BLE001
            return {}

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
    ) -> tuple[str, str]:
        """若產出含 [GRILL]，走熱馬桶圈後重試一次執行。無標記則原樣返回。"""
        try:
            from backend.company.raho.escalation import resolve_grill
            from backend.company.raho.mgp import parse_choices, parse_grill_output, strip_protocol_marks
            from backend.company.raho.protocol import mgp_enabled
        except Exception:  # noqa: BLE001
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
        )
        if resolved.get("layer") == 5:
            self.events.emit(CompanyEvent.USER_DECISION_NEEDED, {
                "item_id": item.id,
                "title": item.title,
                "question": "\n".join(i.message for i in issues)[:500],
                "resolution": resolved,
            })
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
        try:
            if timeout_s > 0:
                retried = await asyncio.wait_for(
                    self._execute_with_tool_loop(
                        next_prompt, system_prompt, model, role_type.value, item,
                        llm_kwargs=llm_opts,
                    ),
                    timeout=timeout_s,
                )
            else:
                retried = await self._execute_with_tool_loop(
                    next_prompt, system_prompt, model, role_type.value, item,
                    llm_kwargs=llm_opts,
                )
            kind2, _ = parse_grill_output(retried)
            if kind2 == "clear":
                return retried, next_prompt
            return strip_protocol_marks(retried) or reply, next_prompt
        except Exception as exc:  # noqa: BLE001
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

    # ═══════════════════════════════════════════════════════════
    # 檢查點（Save / Resume）
    # ═══════════════════════════════════════════════════════════

    def to_checkpoint(self, goal: str = "") -> dict[str, Any]:
        """將當前運行狀態序列化為檢查點。

        包含所有工作項、預算、日誌，可用於中斷後恢復。

        Args:
            goal: 目標描述（可選）

        Returns:
            可序列化的檢查點字典
        """
        return {
            "goal": goal,
            "run_id": self._run_id,
            "config_name": self.config.name,
            "timestamp": datetime.now().isoformat(),
            "work_items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "assignee": item.assignee.value if item.assignee else None,
                    "status": item.status.value,
                    "tier": item.tier,
                    "priority": getattr(item, "priority", 0),
                    "dependencies": item.depends_on,
                    "artifacts": item.artifacts,
                    "actual_cost": item.actual_cost,
                    "review_count": getattr(item, "review_count", 0),
                    "created_by": item.created_by.value if item.created_by else None,
                }
                for item in self.work_items._items.values()
            ],
            # 檢查點保留 task_spent 全精度（to_dict 會 round 4 位，
            # 恢復後與原值產生浮點誤差），其餘欄位維持序列化格式
            "budget": {**self.budget.to_dict(), "task_spent": self.budget.task_spent},
            "run_log": self._run_log,
            "campaign": self._campaign,
        }

    def _restore_from_checkpoint(self, data: dict[str, Any]) -> None:
        """從檢查點恢復工作項與預算狀態（內部方法）。"""
        from backend.company.work_item import WorkItem, WorkItemStatus

        restored_items: list[WorkItem] = []
        by_id: dict[str, WorkItem] = {}

        for item_data in data.get("work_items", []):
            item = WorkItem(
                title=item_data["title"],
                description=item_data.get("description", ""),
                assignee=RoleType(item_data["assignee"]) if item_data.get("assignee") else None,
                tier=item_data.get("tier", "routine"),
                created_by=RoleType(item_data["created_by"]) if item_data.get("created_by") else None,
            )
            item.id = item_data["id"]
            item.status = WorkItemStatus(item_data["status"])
            item.artifacts = item_data.get("artifacts", {})
            item.actual_cost = item_data.get("actual_cost", 0.0)
            if hasattr(item, "review_count"):
                item.review_count = item_data.get("review_count", 0)
            if hasattr(item, "priority"):
                item.priority = item_data.get("priority", 0)
            restored_items.append(item)
            by_id[item.id] = item

        # 恢復依賴關係
        for item_data, item in zip(data.get("work_items", []), restored_items):
            for dep_id in item_data.get("dependencies", []):
                if dep_id in by_id:
                    item.depends_on.append(dep_id)

        self.work_items._items = {item.id: item for item in restored_items}

        # 恢復預算
        budget_data = data.get("budget", {})
        if budget_data:
            self.budget._task_spent = budget_data.get("task_spent", 0.0)

        # 恢復日誌與 run_id
        self._run_log = data.get("run_log", [])
        self._run_id = data.get("run_id") or self._run_id
        self._campaign = data.get("campaign") or {}

    @staticmethod
    def from_checkpoint(
        data: dict[str, Any],
        config: CompanyConfig | None = None,
        prompt_config: PromptConfig | None = None,
    ) -> CompanyOrchestrator:
        """從檢查點建立可恢復的 Orchestrator。

        Args:
            data: to_checkpoint() 產生的檢查點字典
            config: 公司配置（若為 None 則使用預設）
            prompt_config: 提示詞配置

        Returns:
            已恢復狀態的 CompanyOrchestrator 實例
        """
        orchestrator = CompanyOrchestrator(
            config=config,
            prompt_config=prompt_config,
        )
        orchestrator._restore_from_checkpoint(data)
        return orchestrator

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

    async def _execute_with_tool_loop(
        self,
        prompt: str,
        system: str,
        model: str | None,
        role_value: str,
        item,
        max_tool_steps: int = 3,
        llm_kwargs: dict | None = None,
    ) -> str:
        """執行 LLM 調用並處理工具調用閉環。

        若 LLM 輸出中包含 tool_call 區塊，則執行工具並將
        Observation 回傳給 LLM 繼續推理，直到產出最終交付物
        或達到最大工具步數。

        Args:
            prompt: 初始提示
            system: 系統提示
            model: LLM 模型
            role_value: 角色名稱（用於工具權限）
            item: 工作項（用於事件與日誌）
            max_tool_steps: 最大工具調用步數

        Returns:
            最終交付物文字
        """
        current_prompt = prompt
        conversation_suffix: list[str] = []

        for step in range(max_tool_steps + 1):
            # 組裝當前提示（含歷史 Observation）
            full_prompt = current_prompt
            if conversation_suffix:
                full_prompt = current_prompt + "\n\n" + "\n\n".join(conversation_suffix)

            raw = await asyncio.to_thread(
                call_llm, full_prompt, system=system, model=model, **(llm_kwargs or {})
            )

            # 解析工具調用
            tool_request = tool_registry.parse_tool_call(raw)
            if tool_request is None:
                # 無工具調用 → 這是最終交付物
                return raw

            # ── 執行工具 ──
            self._log("tool_call", {
                "item_id": item.id,
                "tool": tool_request.tool,
                "args": tool_request.args,
                "step": step + 1,
            }, level=logging.INFO)
            self.events.emit(CompanyEvent.TOOL_CALL, {
                "item_id": item.id,
                "title": item.title,
                "tool": tool_request.tool,
                "args": tool_request.args,
                "step": step + 1,
            })

            allow_tools, catalog_allowed = self._catalog_tool_filter(role_value, item)
            if not allow_tools:
                from backend.company.tools import ToolCallResult

                tool_result = ToolCallResult(
                    tool=tool_request.tool,
                    success=False,
                    error="此角色已停用工具調用（allow_tool_use=false）",
                )
            else:
                tool_result = await asyncio.to_thread(
                    tool_registry.execute,
                    tool_request,
                    role_value,
                    catalog_allowed=catalog_allowed,
                )

            observation = (
                str(tool_result.result)[:3000]
                if tool_result.success
                else f"工具執行失敗：{tool_result.error}"
            )

            self._log("tool_result", {
                "item_id": item.id,
                "tool": tool_request.tool,
                "success": tool_result.success,
                "step": step + 1,
            }, level=logging.INFO)
            self.events.emit(CompanyEvent.TOOL_RESULT, {
                "item_id": item.id,
                "title": item.title,
                "tool": tool_request.tool,
                "success": tool_result.success,
                "observation": observation[:500],
                "step": step + 1,
            })

            # 將 LLM 輸出與 Observation 加入對話歷史
            conversation_suffix.append(raw)
            conversation_suffix.append(f"Observation: {observation}")
            conversation_suffix.append(
                "（請根據以上工具結果繼續完成任務。若還需要工具，請輸出 tool_call 區塊；"
                "若已有足夠資訊，請直接給出最終交付物，不要再輸出 tool_call。）"
            )

        # 達到最大工具步數 → 要求 LLM 給出最終答案
        final_prompt = (
            current_prompt + "\n\n" + "\n\n".join(conversation_suffix)
            + "\n\n（已達到最大工具調用次數，請根據目前所有資訊，直接給出最終交付物。）"
        )
        return await asyncio.to_thread(
            call_llm, final_prompt, system=system, model=model, **(llm_kwargs or {})
        )

    async def _execute_single_item(self, goal: str, item) -> None:
        """根據指派角色執行單一工作項（含重試、超時、角色升級）。"""
        self.work_items.transition(item.id, WorkItemStatus.EXECUTING)
        self.events.emit(CompanyEvent.WORK_ITEM_START, {
            "item_id": item.id, "title": item.title, "assignee": item.assignee.value if item.assignee else None,
        })

        # 取得角色定義
        role_type = item.assignee or RoleType.DEVELOPER
        role_def = self.config.roles.get(role_type)
        if role_def is None:
            role_def = STANDARD_ROLES.get(role_type, STANDARD_ROLES[RoleType.DEVELOPER])

        model = self.budget.resolve_model_for_tier(item.tier)
        runtime = resolve_runtime(role_type.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)
        context = self._build_context(item)
        try:
            from backend.company.raho.scorecard import record_execution

            record_execution(role_type.value)
        except Exception:  # noqa: BLE001
            pass

        # 使用角色專用執行提示（若有）
        role_specific_prompt = self.prompt_config.role_execute_prompts.get(role_type.value, "")

        atomic = item.artifacts.get("atomic_role") or {}
        if atomic.get("system_prompt") or atomic.get("input_ref"):
            from backend.services.commander import l2_task_brief

            prompt = l2_task_brief(
                title=item.title,
                input_ref=atomic.get("input_ref") or item.artifacts.get("input_ref"),
                output_schema=str(atomic.get("output_schema") or ""),
                success_criteria=str(atomic.get("kpi") or atomic.get("success_criteria") or ""),
                allowed_tools=list(atomic.get("allowed_tools") or item.artifacts.get("allowed_tools") or []),
            )
            if context and "輸入指標" not in context:
                prompt = f"{prompt}\n{context}"
        else:
            prompt = self.prompt_config.developer_execute.format(
                goal=goal,
                role_name=role_def.name,
                title=item.title,
                description=item.description,
                context=context,
            )
            if role_specific_prompt:
                prompt = prompt + "\n\n" + role_specific_prompt
        if self._campaign and not atomic.get("input_ref"):
            try:
                from backend.company.raho.planner import CampaignMap

                prompt = prompt + "\n\n" + CampaignMap.from_dict(self._campaign, goal).brief()
            except Exception:  # noqa: BLE001
                pass

        # ── 角色記憶注入：原子角色只讀 input_ref，不灌歷史對話 ──
        if not atomic.get("input_ref"):
            try:
                role_memory = get_role_memory(role_type.value)
                memory_context = await asyncio.to_thread(
                    role_memory.retrieve_formatted, item.title, 3
                )
                if memory_context:
                    prompt = prompt + "\n\n" + memory_context
                    self._log("role_memory_injected", {
                        "item_id": item.id, "role": role_type.value,
                    }, level=logging.DEBUG)
            except Exception:  # noqa: BLE001 - 記憶注入失敗不阻斷執行
                pass

        # 若角色有工具權限，附加工具說明（原子角色只列白名單）
        tools_text = self._get_docker_tools_for_role(role_type, item)
        if tools_text:
            prompt = prompt + "\n\n" + tools_text

        # ── 執行前憲兵檢查：走熱馬桶圈 L3→L4→L5，禁止就地吞掉上交 ──
        try:
            from backend.company.raho.escalation import resolve_grill
            from backend.company.raho.mgp import rule_inspect_instruction
            from backend.company.raho.protocol import mgp_enabled

            if mgp_enabled():
                atomic = item.artifacts.get("atomic_role") or {}
                task_spec = atomic.get("task_layer") if isinstance(atomic, dict) else None
                pre_issues = rule_inspect_instruction(
                    item.title,
                    item.description,
                    tools_allowed=atomic.get("allowed_tools") if isinstance(atomic, dict) else None,
                    task_spec=task_spec,
                )
                if pre_issues:
                    self.events.emit(CompanyEvent.GRILL_RAISED, {
                        "item_id": item.id,
                        "title": item.title,
                        "role": role_type.value,
                        "phase": "preflight",
                        "issues": [i.to_dict() for i in pre_issues],
                    })
                    resolved = await resolve_grill(
                        run_id=self._run_id or item.id,
                        item_id=item.id,
                        goal=goal,
                        title=item.title,
                        description=item.description,
                        issues=pre_issues,
                        assignee=role_type.value,
                        superior="manager",
                    )
                    self._apply_escalation_patch(item, resolved)
                    reply = str(resolved.get("reply") or "").strip()
                    if not reply:
                        reply = (
                            "指令規格不足。請依標題補齊最小交付規格，標註合理假設後繼續，"
                            "不得擴寫範圍。"
                        )
                    prompt = prompt + f"\n\n【上級對執行前質詢的裁決】\n{reply}"
                    item.description = (item.description or "") + f"\n【上級補件】{reply}"
                    if resolved.get("layer") == 5:
                        self.events.emit(CompanyEvent.USER_DECISION_NEEDED, {
                            "item_id": item.id,
                            "title": item.title,
                            "question": "\n".join(i.message for i in pre_issues)[:500],
                            "resolution": resolved,
                            "phase": "preflight",
                        })
                    if resolved.get("timeout"):
                        self.events.emit(CompanyEvent.RAHO_TIMEOUT, {
                            "item_id": item.id, "choice": resolved.get("choice"),
                        })
                    self.events.emit(CompanyEvent.GRILL_RESOLVED, {
                        "item_id": item.id,
                        "layer": resolved.get("layer"),
                        "action": resolved.get("action"),
                        "phase": "preflight",
                        "timeout": bool(resolved.get("timeout")),
                    })
        except Exception:  # noqa: BLE001
            logger.debug("執行前 MGP 略過", exc_info=True)

        # ── 重試迴圈（含指數退避 + 超時 + 角色升級）──
        retry_cfg = self.config.retry_config
        last_error = None
        timeout_s = retry_cfg.deadline_seconds
        if runtime.get("timeout_ms"):
            timeout_s = max(5.0, float(runtime["timeout_ms"]) / 1000.0)
        max_retries = retry_cfg.max_retries
        if runtime.get("max_retries") is not None:
            try:
                max_retries = max(0, min(8, int(runtime["max_retries"])))
            except (TypeError, ValueError):
                max_retries = retry_cfg.max_retries
        if atomic.get("max_iterations") is not None:
            try:
                max_retries = max(0, min(max_retries, int(atomic["max_iterations"])))
            except (TypeError, ValueError):
                pass

        for attempt in range(max_retries + 1):
            import time as _time
            _start_time = _time.monotonic()
            try:
                # ── 工具調用閉環執行（含超時控制）──
                system_prompt = (
                    runtime.get("system_prompt")
                    or role_def.system_prompt
                    or self.prompt_config.developer_execute_system
                )
                try:
                    from backend.company.raho.mgp import apply_mgp_system
                    from backend.company.raho.protocol import mgp_enabled

                    atomic = item.artifacts.get("atomic_role") or {}
                    if role_type == RoleType.TACTICAL_COMMANDER and not atomic.get("system_prompt"):
                        from backend.services.commander import apply_commander_system

                        system_prompt = apply_commander_system(system_prompt)
                    if mgp_enabled():
                        if atomic.get("system_prompt"):
                            system_prompt = atomic["system_prompt"]
                        system_prompt = apply_mgp_system(
                            system_prompt,
                            superior=role_type == RoleType.TACTICAL_COMMANDER,
                        )
                except Exception:  # noqa: BLE001
                    pass
                if timeout_s > 0:
                    raw = await asyncio.wait_for(
                        self._execute_with_tool_loop(
                            prompt, system_prompt, model, role_type.value, item,
                            llm_kwargs=llm_opts,
                        ),
                        timeout=timeout_s,
                    )
                else:
                    raw = await self._execute_with_tool_loop(
                        prompt, system_prompt, model, role_type.value, item,
                        llm_kwargs=llm_opts,
                    )
                raw, prompt = await self._maybe_resolve_mgp(
                    goal, item, role_type, raw, prompt, system_prompt, model, llm_opts, timeout_s,
                )
                try:
                    from backend.company.raho.atomic_executor import parse_failed_output

                    failed = parse_failed_output(raw)
                except Exception:  # noqa: BLE001
                    failed = None
                if failed:
                    last_error = f"原子任務失敗：{(failed.get('partial_output') or '')[:240]}"
                    item.artifacts["partial_output"] = failed.get("partial_output") or ""
                    item.artifacts["atomic_status"] = "FAILED"
                    raise RuntimeError(last_error)

                # 記錄成功響應時間（優化 #6）
                elapsed = _time.monotonic() - _start_time
                self._concurrency_stats["success_times"].append(elapsed)

                cost = CostTracker.estimate_cost_rough(model, "high")
                self.budget.record_cost(cost)
                item.actual_cost += cost

                thinking, visible = split_thinking(raw)
                item.artifacts["output"] = visible or raw
                if thinking:
                    item.artifacts["thinking"] = thinking
                self.work_items.request_review(item.id)

                self._log("execute_done", {
                    "item_id": item.id, "title": item.title, "cost": round(cost, 4),
                })
                self.events.emit(CompanyEvent.WORK_ITEM_DONE, {
                    "item_id": item.id,
                    "title": item.title,
                    "cost": round(cost, 4),
                    "role": role_type.value,
                    "output": (visible or raw)[:8000],
                    "thinking": thinking[:4000],
                })

                # ── 角色記憶保存：將執行經驗存入角色記憶 ──
                try:
                    role_memory = get_role_memory(role_type.value)
                    await asyncio.to_thread(
                        role_memory.save_from_work_item,
                        item.title,
                        raw[:1000],
                        None,  # 審查結果稍後由 _review_item 補充
                        True,
                    )
                except Exception:  # noqa: BLE001 - 記憶保存失敗不阻斷流程
                    pass
                try:
                    from backend.company.raho.atomic_pool import recycle as recycle_atomic
                    from backend.company.raho.context_bus import blackboard_record
                    from backend.company.raho.protocol import RahoLayer, raho_enabled

                    if raho_enabled():
                        recycle_atomic(item)
                        blackboard_record(
                            task_id=self._run_id or item.id,
                            layer=RahoLayer.L2_EXECUTOR,
                            title=item.title,
                            content=str(item.artifacts.get("output") or "")[:800],
                            role=role_type.value,
                        )
                except Exception:  # noqa: BLE001
                    pass

                return  # 成功，退出

            except asyncio.TimeoutError:
                last_error = f"執行超時（{retry_cfg.deadline_seconds}s）"
                logger.warning("工作項 %s 超時（attempt %d/%d）", item.id, attempt + 1, retry_cfg.max_retries + 1)
            except Exception as exc:  # noqa: BLE001 - 重試兜底：記錄失敗後繼續下一輪
                last_error = str(exc)
                logger.warning("工作項 %s 失敗（attempt %d/%d）：%s", item.id, attempt + 1, retry_cfg.max_retries + 1, exc)

            # 是否還有重試機會
            if attempt < retry_cfg.max_retries:
                backoff = retry_cfg.retry_backoff_base * (2 ** attempt)
                self.events.emit(CompanyEvent.WORK_ITEM_RETRY, {
                    "item_id": item.id, "attempt": attempt + 1, "backoff": backoff,
                })
                await asyncio.sleep(backoff)

        # ── 所有重試耗盡，嘗試角色升級 ──
        if retry_cfg.enable_escalation and role_type != RoleType.MANAGER:
            superior = self.config.get_superior(role_type)
            if superior and superior in self.config.roles:
                logger.info("工作項 %s 升級：%s → %s", item.id, role_type.value, superior.value)
                self.events.emit(CompanyEvent.WORK_ITEM_ESCALATE, {
                    "item_id": item.id, "from": role_type.value, "to": superior.value,
                })
                item.assignee = superior
                # 遞迴重試（最多一層升級）
                return await self._execute_single_item(goal, item)

        # 最終失敗
        logger.error("工作項 %s 最終失敗：%s", item.id, last_error)
        item.artifacts["error"] = last_error or "未知錯誤"
        self.work_items.block(item.id, f"執行失敗：{last_error}")
        self.events.emit(CompanyEvent.WORK_ITEM_ERROR, {
            "item_id": item.id, "title": item.title, "error": last_error,
        })

    def _task_spec_from_item(self, item) -> dict[str, Any]:
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        layer = artifacts.get("task_layer")
        if isinstance(layer, dict) and layer:
            return layer
        atomic = artifacts.get("atomic_role") if isinstance(artifacts.get("atomic_role"), dict) else {}
        inner = atomic.get("task_layer")
        if isinstance(inner, dict) and inner:
            return inner
        return {
            "task_description": item.description or item.title,
            "input_ref": artifacts.get("input_ref"),
            "allowed_tools": artifacts.get("allowed_tools") or [],
            "success_criteria": artifacts.get("success_criteria") or "",
            "output_schema": artifacts.get("output_schema") or "",
        }

    async def _run_l1_inspect(self, goal: str, item, review_round: int, max_rounds: int):
        """L1 憲兵閘門。規則驗收，不額外呼叫 LLM（除非 EVOL_RAHO_L1_LLM）。"""
        try:
            from backend.company.raho.inspector import (
                VERDICT_APPROVED,
                VERDICT_ESCALATE,
                VERDICT_REWORK,
                InspectorGate,
                source_for_artifacts,
            )
            from backend.company.raho.protocol import RahoLayer, raho_enabled
            from backend.company.raho.store import STORE as _RAHO_STORE
        except Exception:  # noqa: BLE001
            return None
        if not raho_enabled():
            return None
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        if not (
            artifacts.get("task_layer")
            or artifacts.get("atomic_role")
            or artifacts.get("atomic_distill")
        ):
            return None
        output = str(artifacts.get("output") or "")
        spec = self._task_spec_from_item(item)
        source = source_for_artifacts(artifacts, output)
        gate = InspectorGate()
        verdict = gate.inspect(
            spec,
            output,
            source_data=source,
            rework_rounds=max(0, review_round - 1),
            max_rework=max(1, max_rounds),
            node_id=item.id,
            title=item.title,
        )
        item.artifacts["l1_verdict"] = verdict.to_dict()
        item.artifacts["l1_signed"] = verdict.verdict == VERDICT_APPROVED
        self.events.emit(CompanyEvent.INSPECTOR_VERDICT, {
            "item_id": item.id,
            "title": item.title,
            "verdict": verdict.verdict,
            "quality_score": verdict.quality_score,
            "test_results": verdict.test_results,
            "round": review_round,
        })
        if self._run_id:
            target_layer = (
                int(RahoLayer.L2_EXECUTOR)
                if verdict.grill and verdict.grill.target.endswith("Executor")
                else int(RahoLayer.L3_DECOMPOSER)
            )
            node = _RAHO_STORE.add_node(
                self._run_id,
                from_layer=int(RahoLayer.L1_GRILL),
                to_layer=target_layer if verdict.verdict != VERDICT_APPROVED else int(RahoLayer.L2_EXECUTOR),
                kind="inspect",
                summary=(verdict.details or verdict.verdict)[:240],
                status="resolved" if verdict.verdict == VERDICT_APPROVED else "open",
                payload={"item_id": item.id, "verdict": verdict.to_dict()},
                goal=goal,
            )
            if verdict.verdict == VERDICT_APPROVED:
                _RAHO_STORE.resolve_node(self._run_id, node.node_id, "resolved")
        if verdict.verdict == VERDICT_APPROVED:
            return verdict
        if verdict.verdict == VERDICT_REWORK:
            feedback = verdict.details or "L1 憲兵退回重做"
            if verdict.grill:
                feedback = verdict.grill.required_fix or verdict.grill.details or feedback
                self.events.emit(CompanyEvent.GRILL_RAISED, {
                    "item_id": item.id,
                    "title": item.title,
                    "phase": "inspect",
                    "target": verdict.grill.target,
                    "issues": [verdict.grill.to_issue().to_dict()],
                })
            return verdict
        if verdict.verdict == VERDICT_ESCALATE:
            try:
                from backend.company.raho.escalation import resolve_grill

                issues = [verdict.grill.to_issue()] if verdict.grill else []
                if issues:
                    result = await resolve_grill(
                        run_id=self._run_id or item.id,
                        item_id=item.id,
                        goal=goal,
                        title=item.title,
                        description=item.description,
                        issues=issues,
                        assignee=item.assignee.value if item.assignee else "",
                        superior="tactical_commander",
                    )
                    item.artifacts["l1_escalation"] = result
                    reply = str(result.get("reply") or "").strip()
                    if reply:
                        item.description = (item.description or "") + f"\n【L1 呈報後裁決】{reply}"
            except Exception:  # noqa: BLE001
                logger.debug("L1 呈報裁決略過", exc_info=True)
            return verdict
        return verdict

    async def _review_item(self, goal: str, item, max_rounds: int) -> None:
        """L1 憲兵閘門 → Reviewer 審查工作項交付物。"""
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
                except Exception:  # noqa: BLE001
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

            try:
                raw = call_llm(
                    prompt,
                    system=runtime.get("system_prompt") or role_def.system_prompt or self.prompt_config.reviewer_system,
                    model=model,
                    **llm_opts,
                )
                cost = CostTracker.estimate_cost_rough(model, "medium")
                self.budget.record_cost(cost)
                current.actual_cost += cost

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

            except Exception as exc:  # noqa: BLE001 - 審查異常不阻塞交付，記錄後退出審查迴圈
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

    async def _rework_item(self, goal: str, item, feedback: str) -> None:
        """讓 Developer 根據審查回饋修改交付物（含重試）。"""
        self.work_items.transition(item.id, WorkItemStatus.EXECUTING)

        role_type = item.assignee or RoleType.DEVELOPER
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

        # ── 重試迴圈 ──
        retry_cfg = self.config.retry_config
        last_error = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                if retry_cfg.deadline_seconds > 0:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(
                            call_llm,
                            prompt,
                            system=runtime.get("system_prompt")
                            or role_def.system_prompt
                            or self.prompt_config.developer_execute_system,
                            model=model,
                            **llm_opts,
                        ),
                        timeout=retry_cfg.deadline_seconds,
                    )
                else:
                    raw = call_llm(
                        prompt,
                        system=runtime.get("system_prompt")
                        or role_def.system_prompt
                        or self.prompt_config.developer_execute_system,
                        model=model,
                        **llm_opts,
                    )
                cost = CostTracker.estimate_cost_rough(model, "high")
                self.budget.record_cost(cost)
                item.actual_cost += cost

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
            except Exception as exc:  # noqa: BLE001 - 重試兜底：記錄失敗後繼續下一輪
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

        try:
            raw = call_llm(
                prompt,
                system=self.prompt_config.review_synth_merge_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost)

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

        except Exception as exc:  # noqa: BLE001 - 合併失敗降級為分離流程
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

        try:
            raw = call_llm(
                prompt,
                system=runtime.get("system_prompt")
                or role_def.system_prompt
                or self.prompt_config.synthesizer_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost)

            self._log("synthesize_done", {"cost": round(cost, 4)})
            return raw

        except Exception as exc:  # noqa: BLE001 - 降級兜底：整合失敗改為直接拼接產出
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

        try:
            raw = call_llm(
                prompt,
                system=self.prompt_config.manager_decompose_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "medium")
            self.budget.record_cost(cost)

            result = parse_json_response(raw)
            self._log("final_review_done", result)
            return result

        except Exception as exc:  # noqa: BLE001 - 降級兜底：審查異常時自動通過並留痕
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

    # ═══════════════════════════════════════════════════════════
    # 輔助方法
    # ═══════════════════════════════════════════════════════════

    def _build_context(self, item) -> str:
        """收集依賴工作項的交付物作為上下文（RAHO：最小可行上下文）。"""
        deps = []
        for dep_id in item.depends_on or []:
            dep = self.work_items.get(dep_id)
            if dep:
                deps.append(dep)
        try:
            from backend.company.raho.context_bus import downward_context
            from backend.company.raho.protocol import raho_enabled

            if raho_enabled():
                ctx = downward_context(item, deps)
                milestone = (item.artifacts or {}).get("campaign_node") or {}
                if milestone.get("title"):
                    ctx = (
                        f"【所屬戰役節點 {milestone.get('node_id')}】{milestone.get('title')}\n"
                        f"成果：{milestone.get('outcome')}\n"
                        f"成敗：{milestone.get('success_criteria')}\n\n"
                        f"{ctx}"
                    )
                return ctx
        except Exception:  # noqa: BLE001
            pass
        if not deps:
            return "（無依賴上下文）"
        parts = []
        for dep in deps:
            if dep.status == WorkItemStatus.DONE:
                output = dep.artifacts.get("output", "")
                parts.append(f"【依賴工作項：{dep.title}】\n{output[:1000]}")
        return "\n\n".join(parts) if parts else "（無依賴上下文）"

    def _collect_artifacts(self) -> str:
        """收集所有已完成工作項的交付物。"""
        parts = []
        for item in self.work_items.list_all():
            if item.status == WorkItemStatus.DONE:
                output = item.artifacts.get("output", str(item.artifacts))
                review = item.artifacts.get("review_result", {})
                score = review.get("score", "N/A") if isinstance(review, dict) else "N/A"
                parts.append(
                    f"## {item.title}\n"
                    f"審查分數：{score}\n\n"
                    f"{output[:3000]}"
                )
        return "\n\n---\n\n".join(parts) if parts else "（無交付物）"

    def _count_review_rounds(self) -> int:
        """統計總審查輪數。"""
        total = 0
        for item in self.work_items.list_all():
            rounds = item.artifacts.get("review_rounds", 0)
            if isinstance(rounds, (int, float)):
                total += int(rounds)
        return total

    def _log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        degraded: bool = False,
        level: int = logging.DEBUG,
    ) -> None:
        """記錄運行事件（記憶體日誌 + 持久 JSONL sink）。

        每筆記錄帶 run_id / UTC 時間戳 / degraded 標記；
        降級與關鍵事件提升為 INFO 級結構化日誌。
        """
        entry = {
            "ts": utc_now_iso(),
            "run_id": self._run_id,
            "event": event,
            "degraded": degraded,
            **data,
        }
        self._run_log.append(entry)
        append_run_record(entry)
        if degraded:
            level = max(level, logging.INFO)
        logger.log(level, "公司事件：%s %s", event, entry)

    def _persist_bus_event(self, event: CompanyEvent, data: dict[str, Any]) -> None:
        """EventBus 監聽器：將生命週期事件同步寫入持久軌跡 sink。"""
        payload = dict(data)
        record = {
            "ts": utc_now_iso(),
            "run_id": self._run_id,
            "source": "eventbus",
            "event": event.value,
            "degraded": bool(payload.get("degraded", False)),
            **payload,
        }
        append_run_record(record)

    def _check_docker_budget(self) -> tuple[bool, str]:
        """檢查總預算（API＋Docker＋阿里雲）是否可繼續。

        公司全權控制雲資源預算：當預算壓力過高時，
        自動建議停止非核心容器以節省成本。

        Returns:
            (can_continue, reason): 是否可繼續執行
        """
        pressure = self.budget.budget_pressure

        if pressure >= 1.0:
            return False, (
                f"預算已耗盡（壓力 {pressure:.0%}），"
                f"總花費 ${self.budget.total_spent:.4f}"
                f"（API ${self.budget.api_cost:.4f}"
                f" + Docker ${self.budget.docker_cost:.4f}"
                f" + 阿里雲 ${self.budget.aliyun_cost:.4f}）"
            )

        if pressure >= 0.85:
            return False, (
                f"預算接近上限（壓力 {pressure:.0%}），"
                f"建議先停止非核心容器再繼續"
            )

        if pressure >= self.budget.config.warn_threshold:
            return True, (
                f"預算壓力 {pressure:.0%}，建議檢查容器優化方案"
            )

        return True, "預算充足（API＋雲資源），可正常運行"

    def _apply_docker_optimization(self, suggestions: list[dict[str, Any]]) -> dict[str, Any]:
        """根據優化建議自動停止容器。

        當預算壓力超過 90% 時，自動執行高優先級建議（停止非核心容器）。

        Args:
            suggestions: get_docker_optimization_suggestions() 的回傳值

        Returns:
            執行結果 {stopped: [svc], failed: [svc], saved_per_hour: float}
        """
        from backend.services.docker_manager import get_docker_manager

        dm = get_docker_manager()
        result: dict[str, Any] = {"stopped": [], "failed": [], "saved_per_hour": 0.0}

        if not dm.available or not suggestions:
            return result

        for s in suggestions:
            if s["action"] != "stop":
                continue
            svc = s["service"]
            try:
                dm.stop_container(svc)
                result["stopped"].append(svc)
                result["saved_per_hour"] += s["estimated_saving_per_hour"]
                self._log("docker_stop", {
                    "service": svc,
                    "reason": s["reason"],
                    "saving_per_hour": s["estimated_saving_per_hour"],
                }, degraded=True, level=logging.WARNING)
            except Exception as e:
                result["failed"].append(svc)
                logger.error("自動停止容器 %s 失敗：%s", svc, e)

        return result

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
        created = []
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

    def _error_result(self, message: str) -> dict[str, Any]:
        """產出錯誤結果。"""
        return {
            "success": False,
            "run_id": self._run_id,
            "error": message,
            "kanban": self.work_items.get_kanban(),
            "budget": self.budget.to_dict(),
            "run_log": self._run_log,
            "raho": self._raho_snapshot(),
            "campaign": self._campaign,
            "battle_plan": self._battle_plan,
            "commander": self._commander,
        }

    # ═══════════════════════════════════════════════════════════
    # Docker 工具集成
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _catalog_tool_filter(role_value: str, item=None) -> tuple[bool, list[str] | None]:
        """角色目錄 ∩ L3 原子白名單。空列表 = 不額外限制（除非原子角色指定）。"""
        from backend.company.role_catalog import resolve_runtime

        runtime = resolve_runtime(role_value)
        if runtime.get("allow_tool_use") is False:
            return False, None
        allowed = [str(row).strip() for row in (runtime.get("tools_allowed") or []) if str(row).strip()]
        atomic_tools: list[str] = []
        if item is not None:
            artifacts = getattr(item, "artifacts", None) or {}
            atomic = artifacts.get("atomic_role") if isinstance(artifacts, dict) else {}
            raw = []
            if isinstance(atomic, dict):
                raw = list(atomic.get("allowed_tools") or [])
            if not raw and isinstance(artifacts, dict):
                raw = list(artifacts.get("allowed_tools") or [])
            atomic_tools = [str(t).strip() for t in raw if str(t).strip()]
        if atomic_tools:
            if allowed:
                merged = [t for t in allowed if t in atomic_tools]
                return True, merged or atomic_tools
            return True, atomic_tools
        return True, (allowed or None)

    def _get_docker_tools_for_role(self, role_type: RoleType, item=None) -> str:
        """獲取角色可用的工具說明文字（使用新工具註冊表）。

        包含 Docker、記憶、實驗室與 Minecraft MCP 等該角色可用的工具。
        若角色無可用工具或已停用工具，回傳空字串。
        """
        allow_tools, catalog_allowed = self._catalog_tool_filter(role_type.value, item)
        if not allow_tools:
            return ""
        return tool_registry.format_tools_prompt(
            role_type.value, catalog_allowed=catalog_allowed
        )

    def execute_docker_request(self, tool_name: str, args: dict[str, Any] | None = None) -> str:
        """執行 Docker 工具請求（供外部調用）。

        Args:
            tool_name: 工具名稱
            args: 工具參數

        Returns:
            格式化結果字串
        """
        dm = self.docker or get_docker_manager()
        return execute_docker_tool(tool_name, args, manager=dm)

    def get_docker_status(self) -> dict[str, Any]:
        """獲取 Docker 狀態摘要（供 API 與 UI 使用）。"""
        dm = self.docker or get_docker_manager()
        return {
            "available": dm.available,
            "containers": dm.list_containers(),
            "health": dm.health_check() if dm.available else {"_error": "Docker 不可用"},
        }