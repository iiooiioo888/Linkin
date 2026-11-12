"""L2 原子執行者：憲法層（唯讀）＋任務層工廠＋戰前檢查＋結構化 Grill。

L2 只負責戰前檢查與專注執行。產出必須交給獨立的 L1 憲兵審查官簽核。
L3 只能注入任務層欄位；憲法層寫死在工廠，優先級高於所有後續指令。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線 = 38）不變；子模組：
- constants：憲法／任務層標記、阻塞類型、預設護欄與檢查 regex
- models：AtomicTaskSpec、GrillMessage
- helpers：spec 正規化與文字／工具轉換
- prompt：憲法層 prompt 與任務層 render
- executor：戰前檢查、結構化協議解析、AtomicExecutorFactory
"""

from __future__ import annotations

import json  # noqa: F401
import re  # noqa: F401
from dataclasses import asdict, dataclass, field  # noqa: F401
from typing import Any  # noqa: F401

from backend.company.raho.protocol import (  # noqa: F401
    ESCALATE_MARK,
    GRILL_MARK,
    MAX_SUPERIOR_ROUNDS,
    GrillIssue,
)

from .constants import (  # noqa: F401
    _EMPTY_REFS,
    _FAILED_JSON,
    _GRILL_JSON,
    _LARGE_INPUT,
    _MEASURABLE,
    _SUBJECTIVE_ONLY,
    _TINY_OUTPUT,
    BLOCKER_CAPACITY,
    BLOCKER_CONSTRAINT,
    BLOCKER_CRITERIA,
    BLOCKER_INPUT,
    BLOCKER_TOOL,
    BLOCKER_TYPES,
    CONSTITUTION_MARKER,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_TOKEN_BUDGET,
    GRILL_TARGET_L3,
    GRILL_TARGET_L4,
    GRILL_TARGET_L5,
    MIN_RETRY_ITERATIONS,
    MIN_TOKEN_BUDGET,
    TASK_LAYER_MARKER,
)
from .executor import (
    AtomicExecutorFactory,
    escalate_grill,
    parse_failed_output,
    parse_structured_protocol,
    preflight_issues,
    run_preflight,
)
from .helpers import _as_text, _as_tools, _is_empty_ref, spec_from_mapping  # noqa: F401
from .models import AtomicTaskSpec, GrillMessage
from .prompt import CONSTITUTION_LAYER, has_constitution, render_task_layer

__all__ = [
    "BLOCKER_CAPACITY",
    "BLOCKER_CONSTRAINT",
    "BLOCKER_CRITERIA",
    "BLOCKER_INPUT",
    "BLOCKER_TOOL",
    "BLOCKER_TYPES",
    "CONSTITUTION_LAYER",
    "CONSTITUTION_MARKER",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_TOKEN_BUDGET",
    "TASK_LAYER_MARKER",
    "AtomicExecutorFactory",
    "AtomicTaskSpec",
    "GrillMessage",
    "escalate_grill",
    "has_constitution",
    "parse_failed_output",
    "parse_structured_protocol",
    "preflight_issues",
    "render_task_layer",
    "run_preflight",
    "spec_from_mapping",
]

# 移除子模組在套件上的屬性，維持 dir() 非底線名稱與原單檔模組一致（38 個）。
for _submodule in ("constants", "executor", "helpers", "models", "prompt"):
    globals().pop(_submodule, None)
del _submodule
