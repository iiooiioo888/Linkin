"""思考過程記錄器（Trace Logger）。

完整記錄任務執行過程中的所有記憶、上下文、思考過程：
- LLM 調用（prompt、response、model、cost、耗時）
- 上下文注入（記憶檢索結果、依賴產物、角色記憶）
- 評估/反思的完整內容
- 工具調用與結果
- 階段切換與狀態快照

寫入 backend/data/traces/<task_id>.jsonl，每行一個事件。
支持斷點續跑：任務恢復時可讀取已有軌跡。

本檔案已於第八輪重構拆為套件：對外仍以
from backend.services.trace_logger import TraceLogger, save_checkpoint 等名稱匯入；
實作分散在 paths／logger／checkpoints／traces／stats 等模組，內容與行為逐字不變。
"""

from __future__ import annotations

# 以下 7 個名稱是重構前模組的順帶轉出（dir() 公開集合的一部分），保留以維持相容
import json  # noqa: F401
import logging
import os  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401

from .checkpoints import (  # noqa: F401
    delete_checkpoint,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)
from .logger import TraceLogger  # noqa: F401
from .paths import (  # noqa: F401
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_TRACE_DIR,
    checkpoint_dir,
    checkpoint_path,
    eval_trace_kwargs,
    trace_dir,
    trace_path,
    utc_now_iso,
)
from .stats import aggregate_llm_call_stats, aggregate_reflection_stats  # noqa: F401
from .traces import delete_trace, list_traces, read_trace, trace_event_counts  # noqa: F401

logger = logging.getLogger(__name__)

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in (
    "checkpoints", "paths", "stats", "traces"
):
    globals().pop(_submodule, None)
del _submodule
