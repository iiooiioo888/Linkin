"""EvoLoop LangGraph 節點實作（Task 1.3 / 1.4 / 8.6）。

每個節點接收 EvoLoopState，回傳需要更新的部份欄位。

本檔案已於第十三輪重構拆為套件：對外仍以
from backend.core.nodes import generate_initial_answer, evaluate_answer 等名稱匯入；
實作分散在 length／memory／prompt_build／generate／reflect／finalize／archive 等模組，
call_llm 與 _memory_store 內部一律經 _compat 延遲解析套件層屬性，既有 patch 表面全部有效。
"""

# 注意：原 nodes.py 沒有 from __future__ import annotations；套件層也不加，
# 否則 dir() 會多出公開名稱 annotations（重構前基線沒有）。
# 以下名稱是重構前模組的順帶轉出（dir() 公開集合的一部分），保留以維持相容
import asyncio  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
from typing import Any, Literal, cast  # noqa: F401

from backend.core.evaluation import CrossModelEvaluator, get_evaluator  # noqa: F401
from backend.core.llm import call_llm, parse_json_response  # noqa: F401
from backend.core.pipeline_trace import log_node  # noqa: F401
from backend.core.stage_router import resolve_stage_model  # noqa: F401
from backend.core.state import StateInput  # noqa: F401
from backend.prompts import templates  # noqa: F401
from backend.prompts.templates import truncate  # noqa: F401
from backend.services.archiver import (  # noqa: F401
    save_session_archive,
    save_session_archive_sync,
)

from .archive import archive_state  # noqa: F401
from .finalize import decide_final_answer, finalize_task_answer  # noqa: F401
from .generate import evaluate_answer, generate_initial_answer  # noqa: F401

# 舊模組私有 helper／class 的頂層名稱相容（all-names 基線）
from .length import (  # noqa: F401  # noqa: F401
    MAX_LENGTH_REWRITES,
    _enforce_output_length,
    _env_bool,
    _fail_closed_on_length,
    _length_compliance,
    _max_length_rewrites,
    _min_length_accept_ratio,
    _resolve_output_limit,
    enforce_final_length,
    enforce_output_length,
    length_gate_event_fields,
)
from .memory import (  # noqa: F401  # noqa: F401
    _compress_history_turn,
    _format_history,
    _format_memories,
    _memory_store,
    _search_reflection_hints,
    _TenantMemoryProxy,
    retrieve_memories,
    save_memory,
)
from .prompt_build import (  # noqa: F401
    _format_injected_context,
    _generate_system_prompt,
    build_generate_prompt,
)
from .reflection import (  # noqa: F401
    _length_requirement,
    improve_answer,
    reflect,
)

logger = logging.getLogger(__name__)

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in ("archive", "finalize", "generate", "length", "memory", "prompt_build", "reflection"):
    globals().pop(_submodule, None)
del _submodule
