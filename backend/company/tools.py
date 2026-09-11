"""Agent 工具調用框架。

提供結構化的工具註冊、權限控制與執行機制，取代原有的
Prompt 注入方式。支援：

- 工具註冊表：名稱、描述、參數 schema、執行函數
- 角色權限控制：按角色過濾可用工具
- ReAct 格式解析：解析 LLM 輸出中的工具調用請求
- 安全執行：超時控制、錯誤處理

工具調用格式（LLM 輸出）：
```tool_call
{"tool": "web_search", "args": {"query": "Python asyncio"}}
```
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 工具調用正則（匹配 ```tool_call ... ``` 區塊）
TOOL_CALL_PATTERN = re.compile(
    r"```tool_call\s*\n?(.*?)\n?```",
    re.DOTALL,
)


@dataclass
class ToolDefinition:
    """工具定義。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema 格式
    execute: Callable[..., Any]
    # 允許使用此工具的角色列表（空列表 = 所有角色）
    allowed_roles: list[str] = field(default_factory=list)
    # 是否為只讀工具（只讀工具權限更寬鬆）
    readonly: bool = True
    # 超時秒數
    timeout_seconds: float = 30.0


@dataclass
class ToolCallRequest:
    """解析後的工具調用請求。"""

    tool: str
    args: dict[str, Any]
    raw: str = ""


@dataclass
class ToolCallResult:
    """工具執行結果。"""

    tool: str
    success: bool
    result: Any = None
    error: str = ""


class ToolRegistry:
    """工具註冊表：管理所有可用工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        execute: Callable[..., Any],
        allowed_roles: list[str] | None = None,
        readonly: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        """註冊工具。"""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            execute=execute,
            allowed_roles=allowed_roles or [],
            readonly=readonly,
            timeout_seconds=timeout_seconds,
        )
        logger.debug("工具註冊：%s", name)

    def get(self, name: str) -> ToolDefinition | None:
        """獲取工具定義。"""
        return self._tools.get(name)

    @staticmethod
    def _role_matches(role: str, allowed_roles: list[str]) -> bool:
        if role in allowed_roles:
            return True
        if role.startswith("custom_") and role[7:] in allowed_roles:
            return True
        if f"custom_{role}" in allowed_roles:
            return True
        for token in allowed_roles:
            if token.endswith("*") and role.startswith(token[:-1]):
                return True
        return False

    def _role_permitted(self, tool: ToolDefinition, role: str | None) -> bool:
        if role is None or not tool.allowed_roles:
            return True
        if self._role_matches(role, tool.allowed_roles):
            return True
        return bool(tool.readonly)

    def list_tools(
        self,
        role: str | None = None,
        *,
        catalog_allowed: list[str] | None = None,
    ) -> list[ToolDefinition]:
        """列出可用工具（按角色與目錄 tools_allowed 過濾）。

        Args:
            role: 角色名稱，None 表示列出所有工具
            catalog_allowed: 角色目錄非空 tools_allowed 時取交集；None/空 = 不額外限制

        Returns:
            該角色可用的工具列表
        """
        if role is None:
            result = list(self._tools.values())
        else:
            result = [tool for tool in self._tools.values() if self._role_permitted(tool, role)]
        if catalog_allowed:
            allowed = set(catalog_allowed)
            result = [tool for tool in result if tool.name in allowed]
        return result

    def format_tools_prompt(
        self,
        role: str | None = None,
        *,
        catalog_allowed: list[str] | None = None,
    ) -> str:
        """生成工具說明文字（注入 Prompt）。

        Args:
            role: 角色名稱，用於過濾可用工具
            catalog_allowed: 角色目錄 tools_allowed 交集（空則不額外限制）

        Returns:
            格式化的工具說明，若無可用工具則回傳空字串
        """
        tools = self.list_tools(role, catalog_allowed=catalog_allowed)
        if not tools:
            return ""

        lines = ["【可用的工具】", "你可以使用以下工具來完成任務。若需使用工具，請在回覆中輸出："]
        lines.append('```tool_call')
        lines.append('{"tool": "<工具名>", "args": {<參數>}}')
        lines.append('```')
        lines.append("")
        lines.append("工具列表：")
        for tool in tools:
            params_desc = ", ".join(
                f"{k}: {v.get('description', v.get('type', 'any'))}"
                for k, v in tool.parameters.items()
            ) if tool.parameters else "無參數"
            readonly_tag = "（只讀）" if tool.readonly else "（控制）"
            lines.append(f"- {tool.name}{readonly_tag}: {tool.description}")
            lines.append(f"  參數：{params_desc}")
        lines.append("")
        lines.append("注意：每次只能調用一個工具。調用後請等待結果，再決定下一步。")
        return "\n".join(lines)

    def parse_tool_call(self, text: str) -> ToolCallRequest | None:
        """解析 LLM 輸出中的工具調用請求。

        Args:
            text: LLM 輸出的文字

        Returns:
            ToolCallRequest 或 None（無工具調用）
        """
        match = TOOL_CALL_PATTERN.search(text)
        if not match:
            return None

        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
            tool_name = data.get("tool", "")
            args = data.get("args", {})
            if not tool_name:
                return None
            return ToolCallRequest(tool=tool_name, args=args, raw=raw)
        except json.JSONDecodeError:
            logger.warning("工具調用解析失敗：%s", raw[:200])
            return None

    def execute(
        self,
        request: ToolCallRequest,
        role: str | None = None,
        *,
        catalog_allowed: list[str] | None = None,
    ) -> ToolCallResult:
        """執行工具調用。

        Args:
            request: 工具調用請求
            role: 調用者角色（用於權限檢查）
            catalog_allowed: 角色目錄 tools_allowed 交集（空則不額外限制）

        Returns:
            ToolCallResult
        """
        tool = self.get(request.tool)
        if tool is None:
            return ToolCallResult(
                tool=request.tool,
                success=False,
                error=f"未知工具：{request.tool}",
            )

        # 權限檢查
        if role and not self._role_permitted(tool, role):
            return ToolCallResult(
                tool=request.tool,
                success=False,
                error=f"角色 {role} 無權使用工具 {request.tool}",
            )
        if catalog_allowed and request.tool not in catalog_allowed:
            return ToolCallResult(
                tool=request.tool,
                success=False,
                error=f"角色目錄未授權工具 {request.tool}",
            )

        try:
            result = tool.execute(**request.args)
            _maybe_bill_tool(request.tool, role=role)
            return ToolCallResult(tool=request.tool, success=True, result=result)
        except TypeError as exc:
            return ToolCallResult(
                tool=request.tool,
                success=False,
                error=f"參數錯誤：{exc}",
            )
        except Exception as exc:
            logger.error("工具 %s 執行失敗：%s", request.tool, exc)
            return ToolCallResult(
                tool=request.tool,
                success=False,
                error=str(exc),
            )


def _maybe_bill_tool(tool_name: str, *, role: str | None = None) -> None:
    try:
        name = (tool_name or "").lower()
        if name.startswith("market_") or name in {"archify_strategies", "strategy_preview"}:
            from backend.billing.metering import meter_quant_call

            meter_quant_call(reference=tool_name, meta={"role": role or ""})
        elif name.startswith("docker_") and name in {"docker_restart", "docker_stop", "docker_start"}:
            from backend.billing.metering import emit_usage_event

            emit_usage_event("docker_control", 5.0, reference=tool_name, meta={"role": role or ""})
        elif name in {"place_block", "break_block", "fill_block", "execute_command"} or "minecraft" in name:
            from backend.billing.metering import meter_minecraft

            blocks = 0
            meter_minecraft(tool_name, blocks=blocks, meta={"role": role or ""})
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 全域工具註冊表
# ═══════════════════════════════════════════════════════════════

tool_registry = ToolRegistry()


def _register_builtin_tools() -> None:
    """註冊內建工具。"""
    from backend.company.docker_tools import execute_docker_tool

    # Docker 工具（向後相容）
    tool_registry.register(
        name="docker_ps",
        description="查詢所有 EvoLoop 容器狀態（名稱、運行狀態、健康狀態、端口）",
        parameters={},
        execute=lambda: execute_docker_tool("docker_ps"),
        readonly=True,
    )
    tool_registry.register(
        name="docker_logs",
        description="讀取指定服務的最近日誌",
        parameters={"service": {"type": "string", "description": "服務名稱"}, "tail": {"type": "integer", "description": "日誌行數（預設 100）"}},
        execute=lambda service, tail=100: execute_docker_tool("docker_logs", {"service": service, "tail": tail}),
        readonly=True,
    )
    tool_registry.register(
        name="docker_stats",
        description="查看所有容器的資源使用統計（CPU、記憶體、網路）",
        parameters={},
        execute=lambda: execute_docker_tool("docker_stats"),
        readonly=True,
    )
    tool_registry.register(
        name="docker_health",
        description="檢查所有服務的健康狀態",
        parameters={},
        execute=lambda: execute_docker_tool("docker_health"),
        readonly=True,
    )
    tool_registry.register(
        name="docker_restart",
        description="重啟指定服務",
        parameters={"service": {"type": "string", "description": "服務名稱"}},
        execute=lambda service: execute_docker_tool("docker_restart", {"service": service}),
        allowed_roles=["manager", "devops"],
        readonly=False,
    )
    tool_registry.register(
        name="docker_stop",
        description="停止指定服務",
        parameters={"service": {"type": "string", "description": "服務名稱"}},
        execute=lambda service: execute_docker_tool("docker_stop", {"service": service}),
        allowed_roles=["manager", "devops"],
        readonly=False,
    )
    tool_registry.register(
        name="docker_start",
        description="啟動指定服務",
        parameters={"service": {"type": "string", "description": "服務名稱"}},
        execute=lambda service: execute_docker_tool("docker_start", {"service": service}),
        allowed_roles=["manager", "devops"],
        readonly=False,
    )

    # 記憶查詢工具
    def _memory_query(query: str, k: int = 3) -> str:
        from backend.memory.vector_store import VectorMemoryStore
        store = VectorMemoryStore()
        results = store.search_similar(query, k=k)
        if not results:
            return "（無相關記憶）"
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['text'][:500]}")
        return "\n".join(lines)

    tool_registry.register(
        name="memory_query",
        description="查詢向量記憶庫中的相關歷史經驗",
        parameters={"query": {"type": "string", "description": "查詢內容"}, "k": {"type": "integer", "description": "回傳筆數（預設 3）"}},
        execute=_memory_query,
        readonly=True,
    )

    # 實驗室整合 — Firecrawl / Prompt Optimizer / Ponytail / Archify
    from backend.services import lab_tools as _lab

    tool_registry.register(
        name="firecrawl_scrape",
        description="抓取網頁並轉為 Markdown（Firecrawl；無 API 金鑰時走輕量模式）",
        parameters={
            "url": {"type": "string", "description": "http/https URL"},
            "only_main_content": {"type": "boolean", "description": "僅主內容（預設 true）"},
        },
        execute=lambda url, only_main_content=True: _lab.firecrawl_scrape(
            url, only_main_content=only_main_content
        ),
        readonly=True,
    )
    tool_registry.register(
        name="firecrawl_search",
        description="網頁搜尋並回傳 Markdown 摘要（需 FIRECRAWL_API_KEY）",
        parameters={
            "query": {"type": "string", "description": "搜尋關鍵字"},
            "limit": {"type": "integer", "description": "結果筆數（1–10，預設 5）"},
        },
        execute=lambda query, limit=5: _lab.firecrawl_search(query, limit=limit),
        readonly=True,
    )
    tool_registry.register(
        name="optimize_prompt",
        description="優化提示詞結構與可執行性（Prompt Optimizer）",
        parameters={
            "prompt": {"type": "string", "description": "原始提示詞"},
            "mode": {"type": "string", "description": "user 或 system"},
            "goal": {"type": "string", "description": "優化目標（可選）"},
        },
        execute=lambda prompt, mode="user", goal="": _lab.optimize_prompt(
            prompt, mode=mode, goal=goal
        ),
        readonly=True,
    )
    tool_registry.register(
        name="ponytail_review",
        description="審查過度工程化並給出可刪除清單（Ponytail）",
        parameters={
            "content": {"type": "string", "description": "程式碼、提示詞或 diff"},
            "kind": {"type": "string", "description": "code、prompt 或 diff"},
        },
        execute=lambda content, kind="code": _lab.ponytail_review(content, kind=kind),
        allowed_roles=["reviewer", "manager", "developer", "architect"],
        readonly=True,
    )
    tool_registry.register(
        name="archify_generate",
        description="由描述生成架構拓撲 IR（Archify）",
        parameters={"description": {"type": "string", "description": "系統/流程描述"}},
        execute=lambda description: _lab.generate_architecture(description),
        readonly=True,
    )
    tool_registry.register(
        name="archify_evoloop",
        description="取得 EvoLoop 內建架構 IR",
        parameters={},
        execute=lambda: _lab.get_evoloop_architecture(),
        readonly=True,
    )
    from backend.company.quant_strategy_maps import archify_strategies as _archify_strategies

    tool_registry.register(
        name="archify_strategies",
        description="把 stock-quant 策略庫編成 Archify IR（總覽／分類／單策略工作流），供可視化與角色引用。",
        parameters={
            "view": {
                "type": "string",
                "description": "overview、data_flow、lifecycle、group 或 strategy",
            },
            "id": {"type": "string", "description": "分類 id（ma…）或策略 id（dual_ma…）"},
        },
        execute=lambda view="overview", id="": _archify_strategies(view=view, id=id),
        readonly=True,
    )

    from backend.company.quant_tools import register_company_tools as _register_quant
    from backend.linkin.minecraft import register_company_tools as _register_mc

    _register_mc(tool_registry)
    _register_quant(tool_registry)

    try:  # 服務器運維智能體工具（本地定制模組，缺失時不影響其他工具註冊）
        from backend.linkin.server_admin import register_company_tools as _register_sa

        _register_sa(tool_registry)
    except ImportError:
        pass


# 模組載入時註冊內建工具
_register_builtin_tools()
