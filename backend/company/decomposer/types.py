"""任務拆分型別：策略列舉、拆分結果模型與預算草稿假設 helper。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _draft_assumptions(result: dict[str, Any]) -> list[Any]:
    draft = result.get("budget_draft")
    if isinstance(draft, dict) and isinstance(draft.get("assumptions"), list):
        return draft["assumptions"]
    return []


# ═══════════════════════════════════════════════════════════════
# 拆分策略
# ═══════════════════════════════════════════════════════════════

class DecompositionStrategy(str, Enum):
    """任務拆分策略。

    - LLM:      利用 LLM 理解目標語義，智能分解（最強大，有成本）
    - TEMPLATE: 基於內建任務模板匹配（快速，適合已知場景）
    - RULE:     簡單關鍵字/規則拆分（零成本，適合簡單任務）
    - AUTO:     自動選擇最優策略（預設）
    """
    LLM = "llm"
    TEMPLATE = "template"
    RULE = "rule"
    AUTO = "auto"


# ═══════════════════════════════════════════════════════════════
# 拆分結果
# ═══════════════════════════════════════════════════════════════

@dataclass
class DecompositionResult:
    """任務拆分結果：包含子工作項描述與執行計劃。"""

    goal: str
    strategy: DecompositionStrategy
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    execution_plan: str = ""
    phases: list[list[int]] = field(default_factory=list)  # 每階段的工作項索引
    meta: dict[str, Any] = field(default_factory=dict)      # 額外元數據

    @property
    def subtask_count(self) -> int:
        return len(self.subtasks)

    @property
    def phase_count(self) -> int:
        return len(self.phases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "strategy": self.strategy.value,
            "subtask_count": self.subtask_count,
            "phase_count": self.phase_count,
            "execution_plan": self.execution_plan,
            "subtasks": self.subtasks,
            "phases": self.phases,
            "meta": self.meta,
        }
