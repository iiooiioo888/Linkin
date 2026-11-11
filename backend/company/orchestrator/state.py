"""協調器狀態 mixin（StateMixin）：初始化、取消控制、檢查點、上下文、日誌與 Docker 預算。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from backend.company.budget import BudgetManager
from backend.company.decomposer import TaskDecomposer
from backend.company.events import CompanyEvent, EventBus
from backend.company.prompts import PromptConfig
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.run_log import append_run_record, utc_now_iso
from backend.company.state import CompanyConfig, CompanyRunState, WorkItemStatus, assignee_token
from backend.company.work_item import WorkItemManager
from backend.services.docker_manager import DockerManager

from ._base import OrchestratorBase

logger = logging.getLogger(__name__)

# _log 與 EventBus 同時發出的結構化事件：避免 JSONL 雙寫
_RUN_LOG_BUS_MIRROR_EVENTS = frozenset({
    "company_start",
    "campaign_planned",
    "decompose_done",
    "tool_call",
    "tool_result",
    "phase",
})


class StateMixin(OrchestratorBase):
    """初始化、取消控制、檢查點、上下文、日誌與 Docker 預算。"""

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
        # 思考過程軌跡掛勾：由 task_manager 注入 TraceLogger(task_id)，
        # 使公司模式的逐次模型調用也進 /tasks/{id}/trace（run_id ≠ task_id）
        self.tracer: Any = None
        self.task_id: str = ""

    def request_cancel(self) -> None:
        """請求取消公司任務（執行迴圈會在下一個檢查點中止）。

        同時把尚未完成的工作項標記為 CANCELLED 終態：在飛協程的結果
        會被丟棄（其後續 transition 因終態而失敗，安全無害），看板與
        任務頁不會再出現「任務已取消但工作項還在執行中」的錯位狀態。
        """
        self.cancel_requested = True
        try:
            self.work_items.cancel_all_pending("任務已被使用者取消")
        except Exception:
            logger.warning("取消時標記工作項失敗（不影響取消）", exc_info=True)
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
                    "assignee": assignee_token(item.assignee),
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
        except Exception:
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
        # 與 EventBus 鏡像重疊的生命週期事件只寫一次 JSONL（由 _persist_bus_event 落盤）
        if event not in _RUN_LOG_BUS_MIRROR_EVENTS:
            append_run_record(entry)
        if degraded:
            level = max(level, logging.INFO)
        logger.log(level, "公司事件：%s %s", event, entry)

    def _persist_bus_event(self, event: CompanyEvent, data: dict[str, Any]) -> None:
        """EventBus 監聽器：公司生命週期事件唯一 JSONL 寫入路徑。"""
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
                dm.stop_service(svc)
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
            pending = [
                p.to_dict()
                for p in STORE.list_pending(run_id)
                if p.resolution is None
            ]
            return {
                "run_id": run_id,
                "tree": tree.to_dict() if tree else None,
                "pending_decisions": pending,
                "campaign": self._campaign or (tree.campaign if tree else {}),
                "battle_plan": self._battle_plan,
                "commander": self._commander,
            }
        except Exception:
            return {}

    def _emit_user_pending(self, pending, *, title: str = "", phase: str = "") -> None:
        """pending 寫入後立刻通知前端，讓 L5 決策列可點。"""
        remaining = max(0.0, float(pending.ttl) - (time.time() - float(pending.created_at)))
        self.events.emit(CompanyEvent.USER_DECISION_NEEDED, {
            "decision_id": pending.decision_id,
            "item_id": pending.item_id,
            "run_id": getattr(pending, "run_id", "") or self._run_id,
            "title": title,
            "question": pending.question,
            "choices": pending.choices,
            "ttl": pending.ttl,
            "created_at": pending.created_at,
            "remaining_sec": round(remaining, 1),
            "blocked": True,
            "phase": phase,
        })
