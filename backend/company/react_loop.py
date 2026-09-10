"""ReAct 執行循環 — Agent 多步推理能力。

實作 Thought → Action → Observation 循環，讓 Agent 能夠：
1. 分析當前狀態（Thought）
2. 選擇並調用工具（Action）
3. 觀察工具結果（Observation）
4. 重複直到得出最終答案（Final Answer）

使用範例：
    >>> from backend.company.react_loop import ReActExecutor
    >>> from backend.company.tools import tool_registry
    >>> executor = ReActExecutor(tool_registry, max_steps=5)
    >>> result = executor.run(
    ...     task="檢查 backend 服務的健康狀態",
    ...     role="devops",
    ...     context="使用者報告 backend 可能當機",
    ... )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.company.tools import ToolCallResult, ToolRegistry
from backend.core.llm import call_llm, llm_kwargs_for_role

logger = logging.getLogger(__name__)

# ReAct 系統提示
REACT_SYSTEM_PROMPT = """你是一位善於推理與使用工具的 AI Agent。

請按照以下格式進行思考與行動：

Thought: 分析當前狀態，思考下一步該做什麼
Action: 若需要工具，輸出工具調用（格式見下方）；若已可回答，輸出 Final Answer
Observation: （系統會填入工具執行結果）

重複以上循環，直到你能給出最終答案。

最終答案格式：
Final Answer: <你的最終回答>

注意事項：
- 每次只能調用一個工具
- 仔細觀察工具結果，再決定下一步
- 若工具執行失敗，分析原因並嘗試其他方法
- 最多執行 {max_steps} 步，若仍無法完成，給出目前最佳答案
"""

# ReAct 使用者提示模板
REACT_USER_PROMPT = """【任務】
{task}

【背景上下文】
{context}

{tools_prompt}

請開始執行任務。先輸出 Thought 分析當前狀態。"""


@dataclass
class ReActStep:
    """ReAct 單步記錄。"""

    step: int
    thought: str = ""
    action: str = ""
    observation: str = ""
    tool_call: dict[str, Any] | None = None
    tool_result: ToolCallResult | None = None


@dataclass
class ReActResult:
    """ReAct 執行結果。"""

    success: bool
    final_answer: str
    steps: list[ReActStep] = field(default_factory=list)
    total_steps: int = 0
    error: str = ""

    @property
    def used_tools(self) -> list[str]:
        """回傳使用過的工具列表。"""
        tools = []
        for step in self.steps:
            if step.tool_call:
                tools.append(step.tool_call.get("tool", ""))
        return [t for t in tools if t]


class ReActExecutor:
    """ReAct 執行器：驅動 Thought → Action → Observation 循環。"""

    def __init__(
        self,
        registry: ToolRegistry,
        max_steps: int = 5,
        model: str | None = None,
    ):
        """初始化 ReAct 執行器。

        Args:
            registry: 工具註冊表
            max_steps: 最大執行步數
            model: LLM 模型（None 使用預設）
        """
        self.registry = registry
        self.max_steps = max_steps
        self.model = model

    def run(
        self,
        task: str,
        role: str | None = None,
        context: str = "",
    ) -> ReActResult:
        """執行 ReAct 循環。

        Args:
            task: 任務描述
            role: 執行角色（用於工具權限）
            context: 背景上下文

        Returns:
            ReActResult
        """
        catalog_allowed = None
        tools_enabled = True
        llm_opts: dict[str, Any] = {}
        model = self.model
        try:
            from backend.company.role_catalog import resolve_runtime

            runtime = resolve_runtime(role or "")
            if runtime.get("preferred_model"):
                model = runtime["preferred_model"]
            llm_opts = llm_kwargs_for_role(runtime)
            if role and runtime.get("allow_tool_use") is False:
                tools_prompt = ""
                tools_enabled = False
            else:
                allowed = [
                    str(item).strip()
                    for item in (runtime.get("tools_allowed") or [])
                    if str(item).strip()
                ]
                catalog_allowed = allowed or None
                tools_prompt = self.registry.format_tools_prompt(
                    role, catalog_allowed=catalog_allowed
                )
        except Exception:
            tools_prompt = self.registry.format_tools_prompt(role)
        system_prompt = REACT_SYSTEM_PROMPT.format(max_steps=self.max_steps)
        
        # 對話歷史（累積 Thought/Action/Observation）
        conversation: list[str] = []
        steps: list[ReActStep] = []

        # 初始提示
        initial_prompt = REACT_USER_PROMPT.format(
            task=task,
            context=context or "（無額外上下文）",
            tools_prompt=tools_prompt,
        )
        conversation.append(initial_prompt)

        for step_num in range(1, self.max_steps + 1):
            step = ReActStep(step=step_num)

            # 組裝當前對話
            current_prompt = "\n\n".join(conversation)

            try:
                response = call_llm(
                    current_prompt,
                    system=system_prompt,
                    model=model,
                    **llm_opts,
                )
            except Exception as exc:
                logger.error("ReAct LLM 調用失敗（step %d）：%s", step_num, exc)
                return ReActResult(
                    success=False,
                    final_answer="",
                    steps=steps,
                    total_steps=step_num,
                    error=f"LLM 調用失敗：{exc}",
                )

            # 檢查是否有 Final Answer
            if "Final Answer:" in response:
                final_answer = response.split("Final Answer:", 1)[1].strip()
                step.thought = response.split("Final Answer:")[0].strip()
                steps.append(step)
                logger.info("ReAct 完成（%d 步）：%s...", step_num, final_answer[:100])
                return ReActResult(
                    success=True,
                    final_answer=final_answer,
                    steps=steps,
                    total_steps=step_num,
                )

            # 解析 Thought
            thought = ""
            if "Thought:" in response:
                thought = response.split("Thought:", 1)[1]
                if "Action:" in thought:
                    thought = thought.split("Action:")[0]
                thought = thought.strip()
            step.thought = thought

            # 解析工具調用
            tool_request = self.registry.parse_tool_call(response)
            if tool_request is None:
                # 無工具調用也無 Final Answer → 提示 LLM 給出答案
                conversation.append(response)
                conversation.append("（請繼續：若已有足夠資訊，請輸出 Final Answer；若需要工具，請輸出 tool_call 區塊）")
                steps.append(step)
                continue

            # 執行工具
            step.tool_call = {"tool": tool_request.tool, "args": tool_request.args}
            step.action = f"調用工具 {tool_request.tool}"
            
            if not tools_enabled:
                from backend.company.tools import ToolCallResult

                tool_result = ToolCallResult(
                    tool=tool_request.tool,
                    success=False,
                    error="此角色已停用工具調用（allow_tool_use=false）",
                )
            else:
                tool_result = self.registry.execute(
                    tool_request, role=role, catalog_allowed=catalog_allowed
                )
            step.tool_result = tool_result

            if tool_result.success:
                observation = str(tool_result.result)[:3000]  # 限制長度
                step.observation = observation
            else:
                observation = f"工具執行失敗：{tool_result.error}"
                step.observation = observation

            # 加入對話歷史
            conversation.append(response)
            conversation.append(f"Observation: {observation}")
            steps.append(step)

            logger.debug(
                "ReAct step %d：tool=%s success=%s",
                step_num,
                tool_request.tool,
                tool_result.success,
            )

        # 達到最大步數
        logger.warning("ReAct 達到最大步數 %d", self.max_steps)
        
        # 最後一次嘗試：要求總結
        try:
            summary_prompt = "\n\n".join(conversation) + "\n\n（已達到最大步數，請根據目前的觀察結果，輸出 Final Answer 總結你的發現。）"
            final_response = call_llm(summary_prompt, system=system_prompt, model=model, **llm_opts)
            if "Final Answer:" in final_response:
                final_answer = final_response.split("Final Answer:", 1)[1].strip()
            else:
                final_answer = final_response
            return ReActResult(
                success=True,
                final_answer=final_answer,
                steps=steps,
                total_steps=self.max_steps,
            )
        except Exception as exc:
            return ReActResult(
                success=False,
                final_answer="",
                steps=steps,
                total_steps=self.max_steps,
                error=f"達到最大步數且總結失敗：{exc}",
            )