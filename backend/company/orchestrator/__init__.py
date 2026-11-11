"""多代理人公司協調器。

將 EvoLoop 反思迴圈擴展為完整的公司運行時，協調多個 AI 角色
分工合作完成複雜目標。核心流程：

  1. TaskDecomposer 接收目標 → 分解為工作項（主功能模組）
  2. 工作項依賴解析 → 平行執行（Developer 角色）
  3. 每個工作項執行完 → Reviewer 審查
  4. 審查不通過 → 退回修改（最多 N 輪）
  5. 所有工作項完成 → Synthesizer 整合
  6. Manager 最終審查 → 產出最終交付物

全程內建預算追蹤與模型層級路由。

任務拆分（TaskDecomposer）已提升為獨立的一級模組，
可脫離 CompanyOrchestrator 單獨使用與測試。

本檔案已於第三輪重構拆為套件：對外仍以
from backend.company.orchestrator import CompanyOrchestrator 匯入，
實作分散在 state／execution／item／tool_loop／review 等 mixin，行為不變。
測試會以 patch(backend.company.orchestrator.call_llm) 注入假 LLM，
因此本模組仍保留 call_llm 的 re-export（相容表面）。
"""

from __future__ import annotations

from typing import Any

from backend.company.prompts import PromptConfig
from backend.company.state import CompanyConfig
from backend.core.llm import call_llm  # noqa: F401

from .execution import ExecutionMixin
from .item import ItemMixin
from .review import ReviewMixin
from .state import StateMixin
from .tool_loop import ToolLoopMixin


class CompanyOrchestrator(StateMixin, ExecutionMixin, ItemMixin, ToolLoopMixin, ReviewMixin):
    """公司協調器：管理多角色分工執行流程。

    任務拆分委派給 TaskDecomposer（獨立主功能模組）。
    """

    @staticmethod
    def from_checkpoint(
        data: dict[str, Any],
        config: CompanyConfig | None = None,
        prompt_config: PromptConfig | None = None,
    ) -> CompanyOrchestrator:
        """從檢查點建立可恢復的 Orchestrator。

        Args:
            data: to_checkpoint() 產生的檢查點字典
            config: 公司配置（若為 None 則使用預設）
            prompt_config: 提示詞配置

        Returns:
            已恢復狀態的 CompanyOrchestrator 實例
        """
        orchestrator = CompanyOrchestrator(
            config=config,
            prompt_config=prompt_config,
        )
        orchestrator._restore_from_checkpoint(data)
        return orchestrator


__all__ = ["CompanyOrchestrator"]
