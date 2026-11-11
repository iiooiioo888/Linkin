"""Context 洞察聚合（對齊 dsh-context 資訊架構）。

從任務軌跡 JSONL 組裝可視化所需結構：
- **stats**：回合／LLM 呼叫／注入／工具／記憶操作計數與估算 token
- **composition**：當前上下文組成（六色類別）
- **trend**：每次 llm_call 為一步的組成趨勢
- **events**：注入／壓縮／剪枝／切換／模式等上下文演進事件
- **browser**：選定步驟的元素清單（可展開內容）

估算採固定密度啟發式（CHARS_PER_TOKEN），與 ContextAssembler 一致；
不做真實 tokenizer，避免測試依賴與供應商差異。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- composition：token 估算、類別鍵、事件分類與檔案用途 helper
- browser：browser 歷史／即時視圖、resolve_default_task_id
- insight：build_context_insight 主聚合
"""

from __future__ import annotations

from typing import Any

from backend.services.trace_logger import list_traces, read_trace, trace_event_counts

from .browser import resolve_default_task_id
from .composition import CHARS_PER_TOKEN, COMPOSITION_KEYS, EVENT_KIND_MAP
from .insight import build_context_insight

__all__ = [
    "CHARS_PER_TOKEN",
    "COMPOSITION_KEYS",
    "EVENT_KIND_MAP",
    "Any",
    "annotations",
    "build_context_insight",
    "list_traces",
    "read_trace",
    "resolve_default_task_id",
    "trace_event_counts",
]
