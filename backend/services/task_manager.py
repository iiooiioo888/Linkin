"""任務管理器：統一模式的後台任務執行。

統一模式下不再區分「標準/公司/OPC」三種模式，所有任務
進入同一條 EvoLoop 管線，由系統自動判斷執行策略：

    POST /tasks          建立任務（回傳 task_id）
    GET  /tasks/{id}     查詢任務進度與結果

持久化（容器重啟不丟失）：
- 任務記錄即時寫入 Redis（`evoloop:task:{task_id}`，TTL 7 天），
  Redis 不可用時降級為純記憶體；重啟後仍在 running 的任務
  會被標記為失敗（服務中斷）
- 任務完成後寫入 JSONL 對話存檔（與 /chat 同一存檔管線）

統一管線流程：
  記憶檢索 → OPC 上下文增強（自動） → 靈境 RAG 增強（自動） → 複雜度路由
    ├─ 工業任務（OPC 可用）→ 6 級閉環（感知→預處理→分析→診斷→決策→執行）
    ├─ 複雜任務 → 公司運行時（分解→執行→審查→整合）
    └─ 簡單任務 → 單次 LLM 生成
  → 評估 → 反思 → 改進（迭代迴圈） → 存檔
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

from backend.company.events import CompanyEvent
from backend.company.orchestrator import CompanyOrchestrator
from backend.company.roles import BUILTIN_TEMPLATES
from backend.core import nodes
from backend.core.company_nodes import (
    _is_complex_task,
    _needs_opc_context,
    enhance_with_opc_context,
)
from backend.linkin.pipeline import (
    enhance_with_linkin_context,
    is_linkin_complex_task,
    prefix_query_with_linkin,
    resolve_linkin_company_template,
)
from backend.core.graph import MAX_ITERATIONS, PASS_THRESHOLD
from backend.services.archiver import save_session_archive_sync
from backend.services.task_broadcaster import task_broadcaster
from backend.services.trace_logger import (
    TraceLogger,
    delete_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from opc_service.act import act_opc
from opc_service.analyze import analyze_opc
from opc_service.decide import decide_opc
from opc_service.diagnose import diagnose_opc
from opc_service.preprocess import preprocess_opc
from opc_service.sense import sense_opc

logger = logging.getLogger(__name__)

# 任務記憶體上限（避免無限增長）
MAX_TASKS = 100
MAX_EVENTS_PER_TASK = 200

# Redis 持久化參數
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TASK_KEY_PREFIX = "evoloop:task:"
TASK_TTL_SECONDS = 7 * 86400


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
        # 斷點續跑：是否有可用的檢查點
        self.resumable = False
        # 控制細項（進階參數）
        self.options: dict[str, Any] = {}
        self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "strategy": self.strategy,
            "resolved_path": self.resolved_path,
            "query": self.query,
            "template": self.template,
            "phase": self.phase,
            "events": self.events[-50:],  # API 回傳最近 50 條
            "kanban": self.kanban,
            "budget": self.budget,
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
        }

    def to_snapshot(self) -> dict[str, Any]:
        """完整快照（供持久化，含全部事件）。"""
        data = self.to_dict()
        data["events"] = self.events
        data["created_at"] = self.created_at
        return data

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "TaskRecord":
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
        return record


class TaskManager:
    """任務管理器（進程內單例，任務記錄持久化到 Redis）。"""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}
        self._redis: redis.Redis | None = None
        self._redis_failed = False
        # 執行中的公司 orchestrator 引用（task_id → orchestrator），供取消使用
        self._orchestrators: dict[str, CompanyOrchestrator] = {}

    # ── Redis 持久化 ──

    def _get_redis(self) -> "redis.Redis | None":
        """惰性取得 Redis 連線；失敗後不再重試（降級為記憶體）。"""
        if self._redis is not None:
            return self._redis
        if self._redis_failed:
            return None
        try:
            import redis
            client = redis.Redis.from_url(
                REDIS_URL, decode_responses=True, socket_connect_timeout=2
            )
            client.ping()
            self._redis = client
            logger.info("任務持久化：Redis 連線成功")
            return client
        except Exception as exc:  # noqa: BLE001
            logger.warning("任務持久化：Redis 不可用，降級為記憶體：%s", exc)
            self._redis_failed = True
            return None

    def _persist(self, record: TaskRecord) -> None:
        """將任務快照寫入 Redis（盡力而為）。"""
        client = self._get_redis()
        if client is None:
            return
        try:
            client.set(
                TASK_KEY_PREFIX + record.task_id,
                json.dumps(record.to_snapshot(), ensure_ascii=False),
                ex=TASK_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("任務持久化寫入失敗：%s", exc)

    def _load_from_redis(self, task_id: str) -> TaskRecord | None:
        client = self._get_redis()
        if client is None:
            return None
        try:
            raw = client.get(TASK_KEY_PREFIX + task_id)
            if not raw:
                return None
            record = TaskRecord.from_snapshot(json.loads(raw))
            # 服務重啟後仍在運行的任務不可能繼續，標記為失敗
            if record.status in ("pending", "running"):
                record.status = "failed"
                record.error = record.error or "後端服務重啟，任務中斷"
                self._persist(record)
            return record
        except Exception as exc:  # noqa: BLE001
            logger.warning("任務記錄讀取失敗：%s", exc)
            return None

    # ── 公開 API ──

    def create_task(
        self, query: str, strategy: str, template: str, options: dict[str, Any] | None = None
    ) -> TaskRecord:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(task_id, query, strategy, template)
        record.options = options or {}
        self.tasks[task_id] = record
        self._persist(record)
        # 簡單淘汰：超出上限時刪除最舊的已完成任務
        if len(self.tasks) > MAX_TASKS:
            finished = [
                t for t in self.tasks.values()
                if t.status in ("completed", "failed")
            ]
            for t in sorted(finished, key=lambda x: x.created_at)[:10]:
                self.tasks.pop(t.task_id, None)
        return record

    def resume_task(self, task_id: str) -> tuple[bool, str]:
        """斷點續跑：從檢查點恢復任務執行。

        僅支援走公司運行時路徑的任務（有 orchestrator checkpoint）。

        Returns:
            (success, message)
        """
        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if record.status == "running":
            return False, "任務正在執行中"
        if record.status == "completed":
            return False, "任務已完成，無需恢復"
        if record.resolved_path != "company":
            return False, "僅公司運行時路徑的任務支持斷點續跑"

        # 檢查是否有檢查點
        checkpoint = load_checkpoint(task_id)
        if checkpoint is None:
            return False, "找不到檢查點，無法恢復"

        # 重置任務狀態
        record.status = "pending"
        record.error = ""
        record.cancel_requested = False
        record.resumable = False
        self._add_event(record, "resume_requested", {"checkpoint_phase": checkpoint.get("phase", "")})
        self._persist(record)

        # 啟動恢復執行
        asyncio.create_task(self._resume_company_task(record, checkpoint))
        logger.info("任務 %s 已啟動斷點續跑", task_id)
        return True, "已啟動斷點續跑"

    def get_task(self, task_id: str) -> TaskRecord | None:
        record = self.tasks.get(task_id)
        if record is not None:
            return record
        # 記憶體沒有（可能是重啟後）→ 從 Redis 恢復
        record = self._load_from_redis(task_id)
        if record is not None:
            self.tasks[task_id] = record
        return record

    def start_task(self, record: TaskRecord) -> None:
        """以背景任務方式啟動（統一管線）。"""
        asyncio.create_task(self._run_unified_task(record))

    def cancel_task(self, task_id: str) -> tuple[bool, str]:
        """請求取消任務。

        設置取消標誌，執行迴圈會在下一個檢查點中止。
        已完成/已失敗的任務無法取消。

        Returns:
            (success, message)
        """
        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if record.status in ("completed", "failed", "cancelled"):
            return False, f"任務已結束（{record.status}），無法取消"
        record.cancel_requested = True
        self._add_event(record, "cancel_requested", {})
        self._persist(record)
        # 公司運行時：傳遞取消請求到 orchestrator
        orchestrator = self._orchestrators.get(task_id)
        if orchestrator is not None:
            orchestrator.request_cancel()
        logger.info("任務 %s 已請求取消", task_id)
        return True, "已請求取消，任務將在下一個檢查點中止"

    def _check_cancelled(self, record: TaskRecord) -> bool:
        """檢查任務是否已被請求取消，若是則標記為 cancelled。"""
        if record.cancel_requested and record.status == "running":
            record.status = "cancelled"
            record.error = "任務已被使用者取消"
            self._set_phase(record, "cancelled")
            return True
        return False

    # ── 事件記錄輔助（每次變更都持久化） ──

    def _set_phase(self, record: TaskRecord, phase: str, **data: Any) -> None:
        record.phase = phase
        record.events.append({
            "ts": time.time(),
            "event": "phase_change",
            "data": {"phase": phase, **data},
        })
        self._persist(record)
        # WebSocket 实时推送（fire-and-forget）
        self._broadcast_event(record.task_id, "phase_change", {"phase": phase, **data})

    def _broadcast_event(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        """Fire-and-forget 广播事件到 WebSocket 订阅者。"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(task_broadcaster.broadcast(task_id, event, data))
        except RuntimeError:
            # 无事件循环时跳过广播（降级为轮询）
            pass

    def _add_event(self, record: TaskRecord, event: str, data: dict[str, Any]) -> None:
        record.events.append({"ts": time.time(), "event": event, "data": data})
        if len(record.events) > MAX_EVENTS_PER_TASK:
            record.events = record.events[-MAX_EVENTS_PER_TASK:]
        self._persist(record)
        # WebSocket 实时推送
        self._broadcast_event(record.task_id, event, data)

    def _finish(self, record: TaskRecord) -> None:
        """任務結束（完成/失敗）：持久化並寫入 JSONL 存檔。"""
        self._persist(record)
        # WebSocket 推送任务完成/失败事件
        self._broadcast_event(record.task_id, "task_finished", {
            "status": record.status,
            "score": record.score,
            "iteration": record.iteration,
            "error": record.error,
        })
        if record.status == "completed":
            self._archive_task(record)

    def _archive_task(self, record: TaskRecord) -> None:
        """將任務結果寫入 JSONL 對話存檔（與 /chat 同一管線）。"""
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "current_answer": record.answer,
            "final_answer": record.answer,
            "score": record.score,
            "iteration": record.iteration,
            "reflections": [],
            "retrieved_memories": [],
            "archive_metadata": {
                "source": "task_api",
                "strategy": record.strategy,
                "resolved_path": record.resolved_path,
                "template": record.template,
            },
        }
        try:
            save_session_archive_sync(state, record.task_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("任務存檔失敗（不影響結果）：%s", exc)

    # ── 執行策略解析 ──

    def _resolve_path(self, record: TaskRecord) -> str:
        """依執行策略與任務內容解析實際執行路徑。

        回傳值：
        - "opc": 工業任務且 OPC 服務可用 → 6 級閉環
        - "company": 複雜任務 → 公司運行時
        - "simple": 簡單任務 → 單次生成
        """
        strategy = record.strategy

        if strategy == "simple":
            return "simple"
        if strategy == "company":
            return "company"

        # auto：依規則判斷
        query = record.query

        # 工業任務優先走 OPC 6 級閉環
        if _needs_opc_context(query):
            return "opc"

        # 靈境世界觀建造／NPC／任務／道具走公司運行時
        if is_linkin_complex_task(query):
            return "company"

        # 複雜任務走公司運行時
        if _is_complex_task(query):
            return "company"

        return "simple"

    # ── 統一管線執行 ──

    async def _run_unified_task(self, record: TaskRecord) -> None:
        """統一模式任務執行入口：解析路徑後分派到對應子流程。"""
        record.status = "running"
        self._persist(record)

        path = self._resolve_path(record)
        record.resolved_path = path
        self._add_event(record, "path_resolved", {"path": path, "strategy": record.strategy})
        logger.info("任務 %s 解析執行路徑：%s（策略：%s）", record.task_id, path, record.strategy)

        if path == "opc":
            await self._run_opc_task(record)
        elif path == "company":
            await self._run_company_task(record)
        else:
            await self._run_simple_task(record)

    # ── 簡單任務執行（單次生成 + 反思迴圈） ──

    async def _run_simple_task(self, record: TaskRecord) -> None:
        """簡單任務：記憶檢索 → OPC 上下文增強 → 生成 → 反思迴圈。"""
        tracer = TraceLogger(record.task_id)
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "history": [],
        }
        try:
            self._set_phase(record, "retrieve_memories")
            tracer.log_phase_change("retrieve_memories")
            state.update(await asyncio.to_thread(nodes.retrieve_memories, state))
            memories = state.get("retrieved_memories", [])
            if memories:
                tracer.log_context_injection(
                    source="memory", items=memories,
                    phase="retrieve_memories", query=record.query,
                )
            if self._check_cancelled(record):
                self._finish(record)
                return

            # OPC 上下文增強（統一管線標準步驟）
            self._set_phase(record, "enhance_opc_context")
            state.update(await asyncio.to_thread(enhance_with_opc_context, state))
            opc_ctx = state.get("opc_context", {})
            if opc_ctx.get("summary"):
                tracer.log_context_injection(
                    source="opc", items=[opc_ctx["summary"]],
                    phase="enhance_opc_context", query=record.query,
                )
            if self._check_cancelled(record):
                self._finish(record)
                return

            # 靈境 RAG 增強（命中世界觀關鍵詞才注入）
            self._set_phase(record, "enhance_linkin_context")
            state.update(await asyncio.to_thread(enhance_with_linkin_context, state))
            linkin_ctx = state.get("linkin_context", {}) or {}
            if linkin_ctx.get("summary"):
                tracer.log_context_injection(
                    source="linkin", items=[linkin_ctx["summary"]],
                    phase="enhance_linkin_context", query=record.query,
                )
            if self._check_cancelled(record):
                self._finish(record)
                return

            self._set_phase(record, "generate")
            tracer.log_phase_change("generate")
            state.update(await asyncio.to_thread(nodes.generate_initial_answer, state))
            tracer.log_llm_call(
                prompt=f"[generate] query={record.query}",
                response=state.get("initial_answer", "")[:2000],
                phase="generate",
            )
            if self._check_cancelled(record):
                self._finish(record)
                return

            await self._run_reflection_loop(record, state, tracer)

            record.answer = state.get("current_answer", "")
            record.score = state.get("score")
            record.iteration = state.get("iteration", 0)
            record.status = "completed"
            tracer.log_phase_change("done")
            self._set_phase(record, "done")
        except Exception as exc:  # noqa: BLE001
            logger.error("簡單任務 %s 執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase=record.phase, recoverable=False)
        self._finish(record)

    # ── 反思迭代迴圈（三條路徑共用） ──

    async def _run_reflection_loop(
        self, record: TaskRecord, state: dict[str, Any], tracer: TraceLogger
    ) -> None:
        """評估 → 反思 → 改進迭代迴圈（直到達標或達最大迭代）。"""
        self._set_phase(record, "evaluate")
        tracer.log_phase_change("evaluate")
        state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
        evaluation = state.get("evaluation", {})
        tracer.log_evaluation(
            score=state.get("score"),
            feedback=evaluation.get("weaknesses", "") if isinstance(evaluation, dict) else str(evaluation),
            iteration=0,
            strengths=evaluation.get("strengths", "") if isinstance(evaluation, dict) else "",
            weaknesses=evaluation.get("weaknesses", "") if isinstance(evaluation, dict) else "",
        )
        self._add_event(record, "evaluation", {
            "score": state.get("score"),
            "iteration": 0,
        })
        if self._check_cancelled(record):
            return

        while (
            state.get("score", 0.0) < PASS_THRESHOLD
            and state.get("iteration", 0) < MAX_ITERATIONS
        ):
            if self._check_cancelled(record):
                return

            self._set_phase(record, "reflect", iteration=state.get("iteration", 0))
            tracer.log_phase_change("reflect", data={"iteration": state.get("iteration", 0)})
            state.update(await asyncio.to_thread(nodes.reflect, state))
            tracer.log_reflection(
                reflection=state.get("critique", ""),
                iteration=state.get("iteration", 0),
                current_answer_preview=state.get("current_answer", "")[:200],
            )

            self._set_phase(record, "improve", iteration=state.get("iteration", 0))
            tracer.log_phase_change("improve", data={"iteration": state.get("iteration", 0)})
            state.update(await asyncio.to_thread(nodes.improve_answer, state))
            tracer.log_improvement(
                improved_answer=state.get("current_answer", ""),
                iteration=state.get("iteration", 0),
                based_on_reflection=state.get("critique", ""),
            )

            self._set_phase(record, "evaluate")
            state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
            evaluation = state.get("evaluation", {})
            tracer.log_evaluation(
                score=state.get("score"),
                feedback=evaluation.get("weaknesses", "") if isinstance(evaluation, dict) else str(evaluation),
                iteration=state.get("iteration", 0),
            )
            self._add_event(record, "evaluation", {
                "score": state.get("score"),
                "iteration": state.get("iteration", 0),
            })

    # ── 公司運行時執行 ──

    def _attach_company_listener(
        self, record: TaskRecord, orchestrator: CompanyOrchestrator
    ) -> None:
        """掛載事件監聽器：收集事件並更新看板快照。"""

        def listener(event: CompanyEvent, data: dict[str, Any]) -> None:
            event_data = {k: v for k, v in data.items() if k != "config"}
            # execution_plan 較大且已存於 record.plan，不重複放入事件流
            if event == CompanyEvent.DECOMPOSE_DONE:
                event_data.pop("execution_plan", None)
            self._add_event(record, event.value, event_data)
            if event == CompanyEvent.PHASE_CHANGE:
                record.phase = str(data.get("phase", ""))
            # 分解完成：即時記錄規劃（供任務頁執行中展示）
            if event == CompanyEvent.DECOMPOSE_DONE:
                record.plan = {
                    "subtask_count": data.get("subtask_count"),
                    "strategy": data.get("strategy"),
                    "execution_plan": data.get("execution_plan"),
                }
            # 每次事件都刷新看板與預算快照
            try:
                record.kanban = {
                    status.value: items
                    for status, items in orchestrator.get_kanban().items()
                }
                record.budget = orchestrator.get_budget_status()
            except Exception:  # noqa: BLE001
                pass

        orchestrator.events.on(listener)

    def _save_company_checkpoint(self, record: TaskRecord, orchestrator: CompanyOrchestrator, phase: str) -> None:
        """保存公司任務檢查點（供斷點續跑）。"""
        try:
            checkpoint_data = orchestrator.to_checkpoint(goal=record.query)
            checkpoint_data["phase"] = phase
            checkpoint_data["template"] = record.template
            save_checkpoint(record.task_id, checkpoint_data)
            record.resumable = True
            self._persist(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("檢查點保存失敗（不影響執行）：%s", exc)

    async def _resume_company_task(self, record: TaskRecord, checkpoint: dict[str, Any]) -> None:
        """從檢查點恢復公司運行時任務執行。"""
        record.status = "running"
        record.phase = "resuming"
        self._persist(record)
        tracer = TraceLogger(record.task_id)
        tracer.log_phase_change("resume", data={"checkpoint_phase": checkpoint.get("phase", "")})

        config = BUILTIN_TEMPLATES.get(record.template)
        if config is None:
            config = BUILTIN_TEMPLATES["quick_task"]

        # 從檢查點恢復 orchestrator
        orchestrator = CompanyOrchestrator.from_checkpoint(checkpoint, config=config)
        self._attach_company_listener(record, orchestrator)
        self._orchestrators[record.task_id] = orchestrator

        try:
            result = await orchestrator.execute(record.query)
        except Exception as exc:  # noqa: BLE001
            logger.error("公司任務 %s 恢復執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase="resume", recoverable=False)
            self._orchestrators.pop(record.task_id, None)
            self._finish(record)
            return
        finally:
            self._orchestrators.pop(record.task_id, None)

        if not result.get("success"):
            error_msg = result.get("error") or result.get("final_output") or "公司運行時恢復執行失敗"
            if record.cancel_requested or "取消" in error_msg:
                record.status = "cancelled"
                record.error = "任務已被使用者取消"
            else:
                record.status = "failed"
                record.error = error_msg
            self._set_phase(record, "cancelled" if record.status == "cancelled" else "failed")
            self._finish(record)
            return

        record.review = result.get("review")
        record.stats = result.get("stats")
        self._persist(record)

        # 公司產出進入評估/反思/改進迭代迴圈
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "current_answer": result.get("final_output", ""),
            "iteration": 0,
            "score": 0.0,
        }
        try:
            await self._run_reflection_loop(record, state, tracer)
        except Exception as exc:  # noqa: BLE001
            logger.warning("任務 %s 評估迴圈失敗（保留公司產出）：%s", record.task_id, exc)

        record.answer = state.get("current_answer", "")
        record.score = state.get("score")
        record.iteration = state.get("iteration", 0)
        record.status = "completed"
        record.resumable = False
        delete_checkpoint(record.task_id)  # 完成後清理檢查點
        self._set_phase(record, "done")
        self._finish(record)

    async def _run_company_task(self, record: TaskRecord) -> None:
        """公司運行時路徑：多角色分工 → 反思迴圈。"""
        tracer = TraceLogger(record.task_id)
        tracer.log_phase_change("starting", data={"template": record.template})

        config = BUILTIN_TEMPLATES.get(record.template)
        if config is None:
            config = BUILTIN_TEMPLATES["quick_task"]

        linkin_state: dict[str, Any] = {
            "query": record.query,
            "company_template": record.template or "quick_task",
        }
        try:
            linkin_state.update(enhance_with_linkin_context(linkin_state))
            linkin_template = resolve_linkin_company_template(linkin_state)
            if linkin_template:
                config = BUILTIN_TEMPLATES.get(linkin_template) or config
            company_query = prefix_query_with_linkin(record.query, linkin_state)
        except Exception:  # noqa: BLE001
            company_query = record.query

        orchestrator = CompanyOrchestrator(config)
        self._attach_company_listener(record, orchestrator)
        # 註冊 orchestrator 引用（供取消使用）
        self._orchestrators[record.task_id] = orchestrator

        try:
            result = await orchestrator.execute(company_query)
        except Exception as exc:  # noqa: BLE001
            logger.error("公司任務 %s 執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase=record.phase, recoverable=False)
            # 失敗時保存檢查點，允許斷點續跑
            self._save_company_checkpoint(record, orchestrator, record.phase)
            self._orchestrators.pop(record.task_id, None)
            self._finish(record)
            return
        finally:
            # 無論成功失敗，清理 orchestrator 引用
            self._orchestrators.pop(record.task_id, None)

        if not result.get("success"):
            error_msg = result.get("error") or result.get("final_output") or "公司運行時執行失敗"
            # 判斷是否為使用者取消
            if record.cancel_requested or "取消" in error_msg:
                record.status = "cancelled"
                record.error = "任務已被使用者取消"
            else:
                record.status = "failed"
                record.error = error_msg
            self._set_phase(record, "cancelled" if record.status == "cancelled" else "failed")
            self._finish(record)
            return

        # ── 提取公司運行細節（供任務頁展示） ──
        record.review = result.get("review")
        record.stats = result.get("stats")
        for entry in result.get("run_log", []):
            if entry.get("event") == "decompose_done":
                record.plan = {
                    "subtask_count": entry.get("subtask_count"),
                    "strategy": entry.get("strategy"),
                    "execution_plan": entry.get("execution_plan"),
                }
                break
        self._persist(record)

        # ── 公司產出進入評估/反思/改進迭代迴圈 ──
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "current_answer": result.get("final_output", ""),
            "iteration": 0,
            "score": 0.0,
        }
        try:
            await self._run_reflection_loop(record, state, tracer)
        except Exception as exc:  # noqa: BLE001
            logger.warning("任務 %s 評估迴圈失敗（保留公司產出）：%s", record.task_id, exc)

        record.answer = state.get("current_answer", "")
        record.score = state.get("score")
        record.iteration = state.get("iteration", 0)
        record.status = "completed"
        self._set_phase(record, "done")
        self._finish(record)

    # ── OPC 6 級閉環執行 ──

    async def _run_opc_task(self, record: TaskRecord) -> None:
        """OPC 6 級閉環路徑：感知→預處理→分析→診斷→決策→執行。

        統一模式下 OPC 不再是獨立模式，而是工業任務的執行路徑。
        6 級結果彙整為回答後，同樣進入反思迭代迴圈。
        """
        tracer = TraceLogger(record.task_id)
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
        }

        try:
            # ── 第 1 級：感知 (Sense) ──
            self._set_phase(record, "sense_opc")
            tracer.log_phase_change("sense_opc")
            state.update(await sense_opc(state))
            record.opc_state["sense"] = {
                "readings": state.get("opc_readings", {}),
                "tag_count": len(state.get("opc_readings", {})),
            }
            self._persist(record)
            if self._check_cancelled(record):
                self._finish(record)
                return

            # ── 第 2 級：預處理 (Preprocess) ──
            self._set_phase(record, "preprocess_opc")
            tracer.log_phase_change("preprocess_opc")
            state.update(await preprocess_opc(state))
            record.opc_state["preprocess"] = {
                "quality_report": state.get("opc_quality_report", {}),
                "clean_count": len(state.get("opc_readings_clean", {})),
            }
            self._persist(record)
            if self._check_cancelled(record):
                self._finish(record)
                return

            # ── 第 3 級：分析 (Analyze) ──
            self._set_phase(record, "analyze_opc")
            tracer.log_phase_change("analyze_opc")
            state.update(await analyze_opc(state))
            record.opc_state["analyze"] = state.get("opc_analysis", {})
            self._persist(record)
            if self._check_cancelled(record):
                self._finish(record)
                return

            # ── 第 4 級：診斷 (Diagnose) ──
            self._set_phase(record, "diagnose_opc")
            tracer.log_phase_change("diagnose_opc")
            state.update(await asyncio.to_thread(diagnose_opc, state))
            record.opc_state["diagnose"] = state.get("opc_diagnosis", {})
            self._persist(record)
            if self._check_cancelled(record):
                self._finish(record)
                return

            # ── 第 5 級：決策 (Decide) ──
            self._set_phase(record, "decide_opc")
            tracer.log_phase_change("decide_opc")
            state.update(await asyncio.to_thread(decide_opc, state))
            record.opc_state["decide"] = {
                "decisions": state.get("opc_decisions", []),
                "summary": state.get("opc_decision_summary", ""),
            }
            self._persist(record)
            if self._check_cancelled(record):
                self._finish(record)
                return

            # ── 第 6 級：執行 (Act) ──
            self._set_phase(record, "act_opc")
            tracer.log_phase_change("act_opc")
            state.update(await act_opc(state))
            record.opc_state["act"] = {
                "actions": state.get("opc_actions", []),
                "action_count": len(state.get("opc_actions", [])),
                "success_count": sum(
                    1 for a in state.get("opc_actions", []) if a.get("success")
                ),
            }

            # ── 彙整 6 級診斷結果為回答 ──
            diagnosis = state.get("opc_diagnosis", {})
            analysis = state.get("opc_analysis", {})
            quality = state.get("opc_quality_report", {})
            decisions = state.get("opc_decisions", [])
            actions = state.get("opc_actions", [])

            answer_parts = ["## OPC 6 級閉環診斷報告\n"]

            # 數據品質
            answer_parts.append(
                f"**數據品質**：總標籤 {quality.get('total', 0)}，"
                f"良好 {quality.get('good', 0)}，不良 {quality.get('bad', 0)}"
            )

            # 分析摘要
            answer_parts.append(f"**統計分析**：{analysis.get('summary', '無')}")

            # 診斷結果
            answer_parts.append(
                f"**診斷結果**：{'⚠️ 檢測到異常' if diagnosis.get('anomaly_detected') else '✅ 無異常'}\n"
                f"- 嚴重程度：{diagnosis.get('severity', 'normal')}\n"
                f"- 根因分析：{diagnosis.get('root_cause', '無')}\n"
                f"- 詳細分析：{diagnosis.get('analysis', '無')}"
            )

            # 決策摘要
            if decisions:
                answer_parts.append(
                    f"**控制決策**：{state.get('opc_decision_summary', '')}"
                )
                for i, d in enumerate(decisions):
                    answer_parts.append(
                        f"{i + 1}. {d.get('tag_name', '?')} → "
                        f"{d.get('value', '?')} "
                        f"（優先級：{d.get('priority', '?')}，"
                        f"風險：{d.get('risk', '?')}）"
                    )
            else:
                answer_parts.append("**控制決策**：無需執行控制動作")

            # 執行結果
            if actions:
                success = sum(1 for a in actions if a.get("success"))
                answer_parts.append(
                    f"**執行結果**：{success}/{len(actions)} 成功"
                )

            # OPC 產出進入反思迭代迴圈
            state["current_answer"] = "\n\n".join(answer_parts)
            state["iteration"] = 0
            state["score"] = 0.0
            try:
                await self._run_reflection_loop(record, state, tracer)
            except Exception as exc:  # noqa: BLE001
                logger.warning("任務 %s 評估迴圈失敗（保留 OPC 產出）：%s", record.task_id, exc)

            record.answer = state.get("current_answer", "")
            record.score = state.get("score")
            record.iteration = state.get("iteration", 0)
            record.status = "completed"

        except Exception as exc:  # noqa: BLE001
            logger.error("OPC 任務 %s 執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase=record.phase, recoverable=False)

        self._set_phase(record, "done")
        self._finish(record)


# 進程內單例
task_manager = TaskManager()