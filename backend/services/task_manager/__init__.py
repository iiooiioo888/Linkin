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
    ├─ 公司（含工業）→ 任務經理分析後席位分工；感測讀數注入目標，寫入經護欄
    └─ 簡單任務 → 單次 LLM 生成
  → 依路徑定稿或反思 → 存檔

本檔案已於第四輪重構拆為套件：對外仍以
from backend.services.task_manager import task_manager, TaskRecord, TaskManager 匯入，
實作分散在 store／lifecycle／budget／runtime／company_runtime 等 mixin，行為不變。
測試會 patch 套件層的 TraceLogger、task_manager 與 enhancement 函式，
因此本模組保留這些相容 re-export（執行期由 _compat 延遲解析）。
"""

from __future__ import annotations

import logging

from backend.core.company_nodes import enhance_with_opc_context
from backend.linkin.pipeline import enhance_with_linkin_context
from backend.services.trace_logger import (
    TraceLogger,
    delete_checkpoint,
    eval_trace_kwargs,
    load_checkpoint,
    save_checkpoint,
)

from ._base import (
    CANCEL_GRACE_SECONDS,
    COMPANY_PERSIST_DEBOUNCE_SEC,
    COMPANY_PERSIST_EVERY_N,
    MAX_EVENTS_PER_TASK,
    MAX_TASKS,
    REDIS_URL,
    TASK_KEY_PREFIX,
    TASK_TTL_SECONDS,
)
from .budget import BudgetMixin
from .company_runtime import CompanyRuntimeMixin
from .lifecycle import LifecycleMixin
from .models import (
    TaskRecord,
    _apply_commander_result,
    _post_company_reflect_mode,
    _task_precomputed_planner,
    _task_ticket,
)
from .runtime import RuntimeMixin
from .store import StoreMixin

logger = logging.getLogger(__name__)


class TaskManager(StoreMixin, LifecycleMixin, BudgetMixin, RuntimeMixin, CompanyRuntimeMixin):
    """任務管理器（進程內單例，任務記錄持久化到 Redis）。"""


# 進程內單例
task_manager = TaskManager()

__all__ = [
    "CANCEL_GRACE_SECONDS",
    "COMPANY_PERSIST_DEBOUNCE_SEC",
    "COMPANY_PERSIST_EVERY_N",
    "MAX_EVENTS_PER_TASK",
    "MAX_TASKS",
    "REDIS_URL",
    "TASK_KEY_PREFIX",
    "TASK_TTL_SECONDS",
    "TaskManager",
    "TaskRecord",
    "TraceLogger",
    "_apply_commander_result",
    "_post_company_reflect_mode",
    "_task_precomputed_planner",
    "_task_ticket",
    "delete_checkpoint",
    "enhance_with_linkin_context",
    "enhance_with_opc_context",
    "eval_trace_kwargs",
    "load_checkpoint",
    "save_checkpoint",
    "task_manager",
]
