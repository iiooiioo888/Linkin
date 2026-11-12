"""預算設定（自 backend.company.state 抽出）。

_default_tier_models 與 BudgetConfig。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import BudgetTier


def _default_tier_models() -> dict[BudgetTier, str]:
    """層級模型預設值：用戶明確配置過 LLM 模型時全部層級跟随該模型。

    確保公司模式與前端/API 配置的供應商（如 Qwen）一致；
    未配置時保持傳統多模型層級預設。
    """
    from backend.core.llm_config import get_explicit_model

    configured = get_explicit_model()
    if configured:
        # 單一供應商場景：所有層級統一使用配置的模型
        return {
            BudgetTier.CRITICAL: configured,
            BudgetTier.REASONING: configured,
            BudgetTier.ROUTINE: configured,
            BudgetTier.SUMMARY: configured,
        }
    return {
        BudgetTier.CRITICAL: "gpt-5.6-sol",
        BudgetTier.REASONING: "gpt-5.6-sol",
        BudgetTier.ROUTINE: "gpt-5.6-luna",
        BudgetTier.SUMMARY: "gpt-5.6-luna",
    }


@dataclass
class BudgetConfig:
    """預算配置：每任務/每會話/每月上限與降級策略。"""

    task_limit_usd: float = 2.0        # 每任務上限（0=不限）
    session_limit_usd: float = 10.0    # 每會話上限
    monthly_limit_usd: float = 100.0   # 每月上限
    warn_threshold: float = 0.8        # 80% 時警告
    degrade_threshold: float = 0.9     # 90% 時降級到便宜模型
    hard_stop: bool = False            # True=超限停止，False=降級繼續

    # 層級路由：每個 tier 對應的模型名稱（預設跟随運行時配置）
    tier_models: dict[BudgetTier, str] = field(default_factory=_default_tier_models)

    # 降級鏈：預算壓力下每個 tier 的備用模型
    # 預設與 tier_models 相同（單一供應商場景無可降級模型）
    degrade_chain: dict[BudgetTier, str] = field(
        default_factory=lambda: {
            tier: model
            for tier, model in _default_tier_models().items()
            if tier in (BudgetTier.CRITICAL, BudgetTier.REASONING)
        }
    )
