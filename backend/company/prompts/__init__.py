"""公司運行時 Prompt 模板。

為每個角色提供專用的系統提示與任務模板，
支援 LLM 驅動的任務分解、執行、審查與整合。

所有提示詞均可透過 PromptConfig 自定義。

套件化：本模組已拆為 backend/company/prompts/ 套件，公開 import 路徑不變。
manager／developer／reviewer／templates／config 各自持有領域 prompt；所有中文字句逐字保留，本 __init__.py 只做 re-export。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import PromptConfig
from .developer import (
    DEVELOPER_EXECUTE,
    DEVELOPER_EXECUTE_SYSTEM,
    ROLE_EXECUTE_PROMPTS,
)
from .manager import (
    MANAGER_DECOMPOSE,
    MANAGER_DECOMPOSE_SYSTEM,
    MANAGER_FINAL_REVIEW,
)
from .reviewer import (
    REVIEW_SYNTH_MERGE,
    REVIEW_SYNTH_MERGE_SYSTEM,
    REVIEWER_REVIEW,
    REVIEWER_SYSTEM,
    SYNTHESIZER_MERGE,
    SYNTHESIZER_SYSTEM,
)
from .templates import (
    GENERIC_DEV_TEMPLATE,
    PAGE_DEV_TEMPLATE,
    RESEARCH_TEMPLATE,
    TEMPLATE_KEYWORDS,
)

__all__ = [
    "DEVELOPER_EXECUTE",
    "DEVELOPER_EXECUTE_SYSTEM",
    "GENERIC_DEV_TEMPLATE",
    "MANAGER_DECOMPOSE",
    "MANAGER_DECOMPOSE_SYSTEM",
    "MANAGER_FINAL_REVIEW",
    "PAGE_DEV_TEMPLATE",
    "RESEARCH_TEMPLATE",
    "REVIEWER_REVIEW",
    "REVIEWER_SYSTEM",
    "REVIEW_SYNTH_MERGE",
    "REVIEW_SYNTH_MERGE_SYSTEM",
    "ROLE_EXECUTE_PROMPTS",
    "SYNTHESIZER_MERGE",
    "SYNTHESIZER_SYSTEM",
    "TEMPLATE_KEYWORDS",
    "Any",
    "PromptConfig",
    "dataclass",
    "field",
]

# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.company.prompts) 的公開名稱與原模組一致（21 個）。
for _submodule in (
    "config",
    "developer",
    "manager",
    "reviewer",
    "templates",
):
    globals().pop(_submodule, None)
del _submodule

