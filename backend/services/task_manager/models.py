"""任務資料模型與模組 helper：TaskRecord（任務快照／持久化）與相容 helper。"""

from __future__ import annotations

import time
from typing import Any

from backend.company.precomputed_planner import normalize_precomputed
from backend.core.post_company_reflect import post_company_reflect_mode


class TaskRecord:
    """單一任務的運行狀態記錄。"""

    def __init__(self, task_id: str, query: str, strategy: str, template: str):
        self.task_id = task_id
        self.query = query
        # 統一模式：執行策略（auto / simple / company），取代原 mode
        self.strategy = strategy
        self.template = template
        self.status = "pending"  # pending / running / completed / failed / cancelled / interrupted
        self.phase = ""
        self.events: list[dict[str, Any]] = []
        self.kanban: dict[str, list[dict]] = {}
        self.budget: dict[str, Any] = {}
        self.budget_plan: dict[str, Any] | None = None
        self.answer = ""
        self.score: float | None = None
        self.iteration = 0
        self.error = ""
        # 取消標誌：任務執行迴圈檢查此標誌以中止執行
        self.cancel_requested = False
        # 公司運行時細節：分解計劃、最終審查結果、工作項統計
        self.plan: dict[str, Any] | None = None
        self.review: dict[str, Any] | None = None
        self.stats: dict[str, Any] | None = None
        # OPC 6 級閉環狀態數據
        self.opc_state: dict[str, Any] = {}
        # 實際採用的執行路徑（simple / company / opc，供前端展示）
        self.resolved_path: str = ""
        self.task_complexity: str = ""
        self.reflection_rounds_max: int = 0
        # 公司路徑：實際執行的公司後反思模式（off / evaluate / full）
        self.post_company_reflect_applied: str | None = None
        # 斷點續跑：是否有可用的檢查點
        self.resumable = False
        # 控制細項（進階參數）
        self.options: dict[str, Any] = {}
        self.created_at = time.time()
        self.finished_at: float | None = None
        self.raho: dict[str, Any] = {}
        self.length_compliance: dict[str, Any] | None = None
        self.length_warning: bool = False
        self.length_refused: bool = False
        self.user_id: str = ""

    def to_dict(self, events_limit: int | None = 50) -> dict[str, Any]:
        """任務快照。events_limit=None 或 0 表示回傳全部事件。"""
        total_events = len(self.events)
        if events_limit is None or events_limit <= 0:
            visible_events = list(self.events)
        else:
            visible_events = self.events[-events_limit:]
        return {
            "task_id": self.task_id,
            "status": self.status,
            "strategy": self.strategy,
            "resolved_path": self.resolved_path,
            "query": self.query,
            "template": self.template,
            "phase": self.phase,
            "events": visible_events,
            "events_total": total_events,
            "events_truncated": total_events > len(visible_events),
            "kanban": self.kanban,
            "budget": self.budget,
            "budget_plan": self.budget_plan,
            "answer": self.answer,
            "score": self.score,
            "iteration": self.iteration,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "plan": self.plan,
            "review": self.review,
            "stats": self.stats,
            "opc_state": self.opc_state,
            "resumable": self.resumable,
            "options": self.options,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "raho": self.raho,
            "length_compliance": self.length_compliance,
            "length_warning": self.length_warning,
            "length_refused": self.length_refused,
            "user_id": self.user_id,
        }

    def to_snapshot(self) -> dict[str, Any]:
        """完整快照（供持久化，含全部事件）。"""
        data = self.to_dict()
        data["events"] = self.events
        data["events_total"] = len(self.events)
        data["events_truncated"] = False
        data["created_at"] = self.created_at
        return data

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> TaskRecord:
        # 向後兼容：舊記錄使用 mode 欄位
        strategy = data.get("strategy") or data.get("mode", "auto")
        record = cls(
            data["task_id"], data.get("query", ""),
            strategy, data.get("template", "quick_task"),
        )
        record.status = data.get("status", "failed")
        record.phase = data.get("phase", "")
        record.events = data.get("events", [])
        record.kanban = data.get("kanban", {})
        record.budget = data.get("budget", {})
        plan = data.get("budget_plan")
        record.budget_plan = plan if isinstance(plan, dict) else None
        record.answer = data.get("answer", "")
        record.score = data.get("score")
        record.iteration = data.get("iteration", 0)
        record.error = data.get("error", "")
        record.plan = data.get("plan")
        record.review = data.get("review")
        record.stats = data.get("stats")
        record.opc_state = data.get("opc_state", {})
        record.resolved_path = data.get("resolved_path", "")
        record.cancel_requested = data.get("cancel_requested", False)
        record.resumable = data.get("resumable", False)
        record.options = data.get("options", {})
        record.created_at = data.get("created_at", time.time())
        finished = data.get("finished_at")
        record.finished_at = float(finished) if finished is not None else None
        record.raho = data.get("raho") or {}
        record.length_compliance = data.get("length_compliance")
        record.length_warning = bool(data.get("length_warning"))
        record.length_refused = bool(data.get("length_refused"))
        record.user_id = str(data.get("user_id") or "").strip()
        return record


def _task_ticket(record: TaskRecord) -> dict[str, Any] | None:
    ticket = (record.options or {}).get("auditor_ticket")
    return ticket if isinstance(ticket, dict) else None

def _task_precomputed_planner(record: TaskRecord) -> dict[str, Any] | None:
    opts = record.options or {}
    return normalize_precomputed(opts.get("precomputed_planner") or opts.get("battle_plan"))

def _post_company_reflect_mode() -> str:
    """相容別名；實作見 ``post_company_reflect_mode``。"""
    return post_company_reflect_mode()

def _apply_commander_result(record: TaskRecord, result: dict[str, Any]) -> None:
    commander = result.get("commander")
    battle = result.get("battle_plan")
    if commander:
        record.raho = {**(record.raho or {}), "commander": commander, **(result.get("raho") or {})}
    if battle:
        record.plan = {
            **(record.plan or {}),
            "strategy": "commander",
            "subtask_count": len(battle.get("dag_nodes") or []),
            "execution_plan": battle.get("plan_id"),
            "battle_plan": battle,
            "commander": commander,
        }
