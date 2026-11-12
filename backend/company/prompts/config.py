"""PromptConfig：可完全自定義的提示詞配置（自 backend.company.prompts 抽出）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .developer import DEVELOPER_EXECUTE, DEVELOPER_EXECUTE_SYSTEM, ROLE_EXECUTE_PROMPTS
from .manager import MANAGER_DECOMPOSE, MANAGER_DECOMPOSE_SYSTEM, MANAGER_FINAL_REVIEW
from .reviewer import (
    REVIEW_SYNTH_MERGE,
    REVIEW_SYNTH_MERGE_SYSTEM,
    REVIEWER_REVIEW,
    REVIEWER_SYSTEM,
    SYNTHESIZER_MERGE,
    SYNTHESIZER_SYSTEM,
)
from .templates import GENERIC_DEV_TEMPLATE, PAGE_DEV_TEMPLATE, RESEARCH_TEMPLATE, TEMPLATE_KEYWORDS

# ═══════════════════════════════════════════════════════════════
# 可自定義提示詞配置
# ═══════════════════════════════════════════════════════════════

@dataclass
class PromptConfig:
    """可完全自定義的提示詞配置。

    所有欄位都有預設值（等於模組級常量），使用者可選擇性覆蓋任一部分。

    使用範例：
        # 使用預設值
        config = PromptConfig()

        # 部分自定義
        config = PromptConfig(
            manager_decompose_system="你是一位敏捷教練...",
            developer_execute="請以 TDD 方式執行...",
        )

        # 透過 CompanyConfig 注入
        company = CompanyConfig(
            prompt_config=PromptConfig(manager_decompose="..."),
        )
    """

    # ── Manager：任務分解 ──
    manager_decompose_system: str = MANAGER_DECOMPOSE_SYSTEM
    manager_decompose: str = MANAGER_DECOMPOSE
    manager_final_review: str = MANAGER_FINAL_REVIEW

    # ── Developer：執行工作項 ──
    developer_execute_system: str = DEVELOPER_EXECUTE_SYSTEM
    developer_execute: str = DEVELOPER_EXECUTE
    role_execute_prompts: dict[str, str] = field(
        default_factory=lambda: dict(ROLE_EXECUTE_PROMPTS)
    )

    # ── Reviewer：審查交付物 ──
    reviewer_system: str = REVIEWER_SYSTEM
    reviewer_review: str = REVIEWER_REVIEW

    # ── Synthesizer：整合交付物 ──
    synthesizer_system: str = SYNTHESIZER_SYSTEM
    synthesizer_merge: str = SYNTHESIZER_MERGE

    # ── Reviewer + Synthesizer 合併 ──
    review_synth_merge_system: str = REVIEW_SYNTH_MERGE_SYSTEM
    review_synth_merge: str = REVIEW_SYNTH_MERGE

    # ── 任務拆分模板 ──
    decompose_templates: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            "page_dev": list(PAGE_DEV_TEMPLATE),
            "generic_dev": list(GENERIC_DEV_TEMPLATE),
            "research": list(RESEARCH_TEMPLATE),
        }
    )
    template_keywords: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: dict(TEMPLATE_KEYWORDS)
    )
