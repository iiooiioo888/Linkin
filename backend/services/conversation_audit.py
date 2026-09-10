"""對話審計編排（TODO §1）。

與 L4 需求審計官（``backend/services/auditor.py``，審「需求」）不同，
本模組審「對話／任務上下文」：**顯式、按需**觸發，時序為

    running（等 inflight 自然結束）→ paused → auditing → 報告 → resume / 保持 paused

契約寫死（對齊 §1.2–§1.6、§9）：

- **C-AUDIT-001**：禁止在串流 done／聊天完成 webhook／插件回調自動觸發或灌入分數。
  本模組不掛任何串流事件；唯一入口是顯式呼叫 ``request_audit``。
- **C-AUDIT-002**：審計前必經「等 inflight → paused」，禁止強制 abort。
- **C-AUDIT-003**：審計失敗預設保持 ``paused``，由用戶顯式選擇恢復或放棄；
  不得靜默寫入假分數。
- **C-AUDIT-004**：快照凍結含插件集合雜湊，雜湊輸入＝插件 ID＋pin 版本＋啟用狀態。
- **C-AUDIT-005**：審計軌跡 append-only、審計流程只讀軌跡；
  清理為顯式管理動作且本身可審計。
- 快照衝突：``resume`` 前校驗版本，不符 → 進入 ``awaiting_confirmation``，
  由用戶選擇「以新上下文重綁」或「放棄任務」（§9.1）。

測試隔離：inflight 等待、審計執行器、快照來源、軌跡存儲全部依賴注入，
預設實作不呼叫 LLM、不寫磁碟（軌跡預設記憶體；JSONL 存儲可選）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from backend.company.task_state_machine import (
    Decision,
    TaskAction,
    TaskRuntimeState,
    Verdict,
    evaluate,
)

logger = logging.getLogger(__name__)

ERR_SNAPSHOT_CONFLICT = "ERR_SNAPSHOT_CONFLICT"
ERR_AUDIT_FAILED = "ERR_AUDIT_FAILED"
ERR_AUDIT_NOT_ALLOWED = "ERR_AUDIT_NOT_ALLOWED"
ERR_TASK_UNKNOWN = "ERR_AUDIT_TASK_UNKNOWN"
ERR_CONFIRM_REQUIRED = "ERR_AWAITING_CONFIRMATION"


# ── 插件集合雜湊（§1.5 寫死） ──────────────────────────────────
@dataclass(frozen=True)
class PluginPin:
    """插件凍結單元：ID＋pin 版本＋啟用狀態；任一變化即視為快照變更。"""

    plugin_id: str
    pin_version: str
    enabled: bool


def compute_plugin_set_hash(plugins: Iterable[PluginPin]) -> str:
    """插件集合雜湊：輸入含 pin 版本，僅升版（啟停不變）也觸發衝突（§1.5）。"""
    rows = sorted(f"{p.plugin_id}@{p.pin_version}:{int(p.enabled)}" for p in plugins)
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


# ── 上下文快照（§1.5 凍結項） ──────────────────────────────────
@dataclass(frozen=True)
class ContextSnapshot:
    conversation_snapshot_id: str
    l0_snapshot_id: str
    seat_schema_version: str
    plugin_set_hash: str
    frozen_at: float = field(default_factory=time.time)

    def diff_against(self, other: ContextSnapshot) -> list[str]:
        """產出快照差異摘要（§9.1：awaiting_confirmation 必須展示衝突詳情）。"""
        diffs: list[str] = []
        if self.conversation_snapshot_id != other.conversation_snapshot_id:
            diffs.append("conversation_snapshot_id")
        if self.l0_snapshot_id != other.l0_snapshot_id:
            diffs.append("l0_snapshot_id")
        if self.seat_schema_version != other.seat_schema_version:
            diffs.append("seat_schema_version")
        if self.plugin_set_hash != other.plugin_set_hash:
            diffs.append("plugin_set_hash")
        return diffs


# ── 審計報告（§1.2：報告為主，分數僅可選欄位） ─────────────────
@dataclass(frozen=True)
class AuditReport:
    task_id: str
    dimensions: tuple[dict[str, Any], ...] = ()   # 維度說明＋依據摘要
    risks: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    score: float | None = None                     # 可選；僅審計完成後出現
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "dimensions": list(self.dimensions),
            "risks": list(self.risks),
            "suggestions": list(self.suggestions),
            "score": self.score,
            "created_at": self.created_at,
        }


# ── 審計軌跡存儲（§1.6：append-only、只讀於審計） ──────────────
class AuditTrailStore(Protocol):
    """審計軌跡存儲契約。

    注意：刻意**沒有** update／delete 介面——審計與插件皆不得修改軌跡（C-AUDIT-005）。
    ``purge`` 是顯式管理動作，本身必須留下可審計記錄（經 admin_log 回調）。
    """

    def append(self, task_id: str, event: dict[str, Any]) -> None: ...

    def read(self, task_id: str) -> tuple[dict[str, Any], ...]: ...

    def purge(self, task_id: str) -> int: ...


class InMemoryAuditTrailStore:
    """預設記憶體實作（測試／骨架用）；生產換 JSONL 或 DB，同級於對話記錄。"""

    def __init__(self, admin_log: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._admin_log = admin_log or (lambda e: logger.info("audit-trail admin: %s", e))

    def append(self, task_id: str, event: dict[str, Any]) -> None:
        self._events.setdefault(task_id, []).append({**event, "at": time.time()})

    def read(self, task_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(self._events.get(task_id, ()))

    def purge(self, task_id: str) -> int:
        count = len(self._events.pop(task_id, []))
        self._admin_log({"action": "purge_audit_trail", "task_id": task_id, "purged": count})
        return count


class JsonlAuditTrailStore:
    """JSONL 持久化（與對話記錄同級；預設保留策略＝對話歷史，可配置）。"""

    def __init__(
        self,
        path: str | Path,
        admin_log: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._path = Path(path)
        self._admin_log = admin_log or (lambda e: logger.info("audit-trail admin: %s", e))

    def append(self, task_id: str, event: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"task_id": task_id, **event, "at": time.time()}, ensure_ascii=False) + "\n")

    def read(self, task_id: str) -> tuple[dict[str, Any], ...]:
        if not self._path.exists():
            return ()
        out: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("task_id") == task_id:
                    out.append(row)
        return tuple(out)

    def purge(self, task_id: str) -> int:
        kept: list[str] = []
        count = 0
        if self._path.exists():
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        kept.append(line)
                        continue
                    if row.get("task_id") == task_id:
                        count += 1
                    else:
                        kept.append(line)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                fh.writelines(kept)
        self._admin_log({"action": "purge_audit_trail", "task_id": task_id, "purged": count})
        return count


# ── 依賴注入契約 ───────────────────────────────────────────────
SnapshotProvider = Callable[[str], ContextSnapshot]
InflightWaiter = Callable[[str], None]
AuditRunner = Callable[[str, ContextSnapshot, tuple[dict[str, Any], ...]], AuditReport]


def default_audit_runner(
    task_id: str, snapshot: ContextSnapshot, trail: tuple[dict[str, Any], ...]
) -> AuditReport:
    """預設啟發式審計（無 LLM）：結構檢查＋軌跡統計。分數僅作可選欄位。"""
    dims = [
        {"name": "trace_completeness", "detail": f"軌跡事件數 {len(trail)}", "evidence": "audit_trail"},
        {"name": "snapshot_frozen", "detail": f"快照凍結於 {snapshot.frozen_at:.0f}", "evidence": "context_snapshot"},
    ]
    return AuditReport(task_id=task_id, dimensions=tuple(dims), score=None)


# ── 任務審計狀態 ───────────────────────────────────────────────
class ConfirmChoice(str, Enum):
    REBIND = "rebind"    # 以新上下文重綁
    ABANDON = "abandon"  # 放棄任務


@dataclass
class AuditTaskState:
    task_id: str
    state: TaskRuntimeState = TaskRuntimeState.RUNNING
    frozen: ContextSnapshot | None = None
    report: AuditReport | None = None
    error: str = ""
    conflict_diff: tuple[str, ...] = ()


class ConversationAuditService:
    """對話審計編排器（§1.4：審計 API 與暫停／恢復解耦但可編排）。"""

    def __init__(
        self,
        *,
        snapshot_provider: SnapshotProvider,
        inflight_waiter: InflightWaiter | None = None,
        audit_runner: AuditRunner = default_audit_runner,
        trail_store: AuditTrailStore | None = None,
        state_evaluator: Callable[[TaskRuntimeState, TaskAction], Decision] = evaluate,
    ) -> None:
        self._snapshot_of = snapshot_provider
        self._wait_inflight = inflight_waiter or (lambda task_id: None)
        self._run_audit = audit_runner
        self._trail = trail_store or InMemoryAuditTrailStore()
        self._evaluate = state_evaluator
        self._tasks: dict[str, AuditTaskState] = {}

    # C-AUDIT-001：刻意不提供任何串流／webhook 掛載點；唯一入口為顯式 request_audit。

    def register_task(self, task_id: str, state: TaskRuntimeState = TaskRuntimeState.RUNNING) -> AuditTaskState:
        task = AuditTaskState(task_id=task_id, state=state)
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> AuditTaskState:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"{ERR_TASK_UNKNOWN}: {task_id}")
        return task

    def request_audit(self, task_id: str, *, scope: str | None = None) -> dict[str, Any]:
        """顯式觸發審計：等 inflight → paused（凍結快照）→ auditing → 報告。

        狀態機守門：非 running／paused／plugin_degraded／awaiting_deploy 狀態下的
        audit 請求依 §9 矩陣拒絕或佇列。
        """
        task = self.get(task_id)
        decision = self._evaluate(task.state, TaskAction.AUDIT)
        if decision.verdict is Verdict.DENY:
            return {"ok": False, "error_code": decision.error_code, "state": task.state.value}
        if decision.verdict is Verdict.QUEUE:
            return {"ok": False, "queued": True, "note": decision.note, "state": task.state.value}

        # §1.3：先等 inflight 自然完成（禁止強制 abort），再進入 paused
        if task.state is TaskRuntimeState.RUNNING:
            self._wait_inflight(task_id)
            task.state = TaskRuntimeState.PAUSED

        # §1.5：進入 paused 時凍結上下文版本號
        if task.frozen is None:
            task.frozen = self._snapshot_of(task_id)

        task.state = TaskRuntimeState.AUDITING
        trail = self._trail.read(task_id)  # C-AUDIT-005：只讀軌跡
        try:
            report = self._run_audit(task_id, task.frozen, trail)
        except Exception as exc:
            logger.warning("審計失敗，任務保持 paused：%s", exc)
            task.state = TaskRuntimeState.PAUSED
            task.error = f"{ERR_AUDIT_FAILED}: {exc}"
            return {
                "ok": False,
                "error_code": ERR_AUDIT_FAILED,
                "state": task.state.value,
                "retryable": True,
            }
        task.report = report
        task.state = TaskRuntimeState.PAUSED  # 展示結果後維持 paused，由用戶選擇恢復
        return {"ok": True, "state": task.state.value, "report": report.to_dict()}

    def resume(self, task_id: str) -> dict[str, Any]:
        """恢復前校驗快照版本；衝突 → awaiting_confirmation（禁止靜默續跑）。"""
        task = self.get(task_id)
        decision = self._evaluate(task.state, TaskAction.RESUME)
        if decision.verdict is Verdict.DENY:
            return {"ok": False, "error_code": decision.error_code, "state": task.state.value}
        if task.frozen is not None:
            current = self._snapshot_of(task_id)
            diffs = task.frozen.diff_against(current)
            if diffs:
                task.state = TaskRuntimeState.AWAITING_CONFIRMATION
                task.conflict_diff = tuple(diffs)
                return {
                    "ok": False,
                    "error_code": ERR_SNAPSHOT_CONFLICT,
                    "state": task.state.value,
                    "conflict_diff": list(diffs),
                }
        task.state = TaskRuntimeState.RUNNING
        return {"ok": True, "state": task.state.value}

    def confirm(self, task_id: str, choice: ConfirmChoice | str) -> dict[str, Any]:
        """§9.1：用戶顯式選擇「重綁」或「放棄」後才能離開 awaiting_confirmation。"""
        task = self.get(task_id)
        if task.state is not TaskRuntimeState.AWAITING_CONFIRMATION:
            return {"ok": False, "error_code": "ERR_NOT_AWAITING_CONFIRMATION", "state": task.state.value}
        choice = ConfirmChoice(choice)
        if choice is ConfirmChoice.REBIND:
            task.frozen = self._snapshot_of(task_id)  # 以新上下文重綁
            task.conflict_diff = ()
            task.state = TaskRuntimeState.PAUSED
            return {"ok": True, "state": task.state.value, "rebound": True}
        # ABANDON：放棄任務（終態由調用方定義；此處標記錯誤並保持不續跑）
        task.error = "abandoned_by_user"
        return {"ok": True, "state": task.state.value, "abandoned": True}

    @property
    def trail(self) -> AuditTrailStore:
        return self._trail


def new_audit_id() -> str:
    return uuid.uuid4().hex[:12]
