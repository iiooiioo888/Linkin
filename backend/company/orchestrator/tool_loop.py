"""工具迴圈 mixin（ToolLoopMixin）：LLM 工具呼叫閉環與 Docker 工具入口。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.company.docker_tools import execute_docker_tool
from backend.company.events import CompanyEvent
from backend.company.roles import RoleType
from backend.company.tools import tool_registry
from backend.services.docker_manager import get_docker_manager

from ._base import OrchestratorBase, _llm_thread
from ._compat import call_llm


class ToolLoopMixin(OrchestratorBase):
    """LLM 工具呼叫閉環與 Docker 工具入口。"""

    async def _execute_with_tool_loop(
        self,
        prompt: str,
        system: str,
        model: str | None,
        role_value: str,
        item,
        max_tool_steps: int = 3,
        llm_kwargs: dict | None = None,
        seat: dict | None = None,
    ) -> str:
        """執行 LLM 調用並處理工具調用閉環。

        若 LLM 輸出中包含 tool_call 區塊，則執行工具並將
        Observation 回傳給 LLM 繼續推理，直到產出最終交付物
        或達到最大工具步數。

        Args:
            prompt: 初始提示
            system: 系統提示
            model: LLM 模型
            role_value: 角色名稱（用於工具權限）
            item: 工作項（用於事件與日誌）
            max_tool_steps: 最大工具調用步數
            seat: 席位投遞脈絡（監察軌跡用，含 context_sources 分解）

        Returns:
            最終交付物文字
        """
        current_prompt = prompt
        conversation_suffix: list[str] = []

        for step in range(max_tool_steps + 1):
            # 組裝當前提示（含歷史 Observation）
            full_prompt = current_prompt
            if conversation_suffix:
                full_prompt = current_prompt + "\n\n" + "\n\n".join(conversation_suffix)

            _call_start = time.monotonic()
            try:
                raw = await _llm_thread(
                    call_llm, full_prompt, system=system, model=model, **(llm_kwargs or {})
                )
            except Exception as exc:
                self._record_seat_io(
                    seat, item, role_value,
                    prompt=full_prompt, system=system, model=model,
                    response="", step=step, llm_kwargs=llm_kwargs,
                    duration_ms=(time.monotonic() - _call_start) * 1000.0,
                    error=str(exc), degraded=True, final=False,
                )
                raise

            tool_request = tool_registry.parse_tool_call(raw)
            if tool_request is None:
                # 無工具調用 → 這是最終交付物
                self._record_seat_io(
                    seat, item, role_value,
                    prompt=full_prompt, system=system, model=model,
                    response=raw, step=step, llm_kwargs=llm_kwargs,
                    duration_ms=(time.monotonic() - _call_start) * 1000.0,
                    tool_steps=step, final=True,
                )
                return raw

            self._record_seat_io(
                seat, item, role_value,
                prompt=full_prompt, system=system, model=model,
                response=raw, step=step, llm_kwargs=llm_kwargs,
                duration_ms=(time.monotonic() - _call_start) * 1000.0,
                tool_steps=step, final=False,
            )

            # ── 執行工具 ──
            self._log("tool_call", {
                "item_id": item.id,
                "tool": tool_request.tool,
                "args": tool_request.args,
                "step": step + 1,
            }, level=logging.INFO)
            self.events.emit(CompanyEvent.TOOL_CALL, {
                "item_id": item.id,
                "title": item.title,
                "tool": tool_request.tool,
                "args": tool_request.args,
                "step": step + 1,
            })

            allow_tools, catalog_allowed = self._catalog_tool_filter(role_value, item)
            if not allow_tools:
                from backend.company.tools import ToolCallResult

                tool_result = ToolCallResult(
                    tool=tool_request.tool,
                    success=False,
                    error="此角色已停用工具調用（allow_tool_use=false）",
                )
            else:
                tool_result = await asyncio.to_thread(
                    tool_registry.execute,
                    tool_request,
                    role_value,
                    catalog_allowed=catalog_allowed,
                )

            observation = (
                str(tool_result.result)[:3000]
                if tool_result.success
                else f"工具執行失敗：{tool_result.error}"
            )

            self._log("tool_result", {
                "item_id": item.id,
                "tool": tool_request.tool,
                "success": tool_result.success,
                "step": step + 1,
            }, level=logging.INFO)
            self.events.emit(CompanyEvent.TOOL_RESULT, {
                "item_id": item.id,
                "title": item.title,
                "tool": tool_request.tool,
                "success": tool_result.success,
                "observation": observation[:500],
                "step": step + 1,
            })

            # 將 LLM 輸出與 Observation 加入對話歷史
            conversation_suffix.append(raw)
            conversation_suffix.append(f"Observation: {observation}")
            conversation_suffix.append(
                "（請根據以上工具結果繼續完成任務。若還需要工具，請輸出 tool_call 區塊；"
                "若已有足夠資訊，請直接給出最終交付物，不要再輸出 tool_call。）"
            )

        # 達到最大工具步數 → 要求 LLM 給出最終答案
        final_prompt = (
            current_prompt + "\n\n" + "\n\n".join(conversation_suffix)
            + "\n\n（已達到最大工具調用次數，請根據目前所有資訊，直接給出最終交付物。）"
        )
        _call_start = time.monotonic()
        final_raw = await asyncio.to_thread(
            call_llm, final_prompt, system=system, model=model, **(llm_kwargs or {})
        )
        self._record_seat_io(
            seat, item, role_value,
            prompt=final_prompt, system=system, model=model, response=final_raw,
            step=max_tool_steps + 1, llm_kwargs=llm_kwargs,
            duration_ms=(time.monotonic() - _call_start) * 1000.0,
            tool_steps=max_tool_steps, final=True,
        )
        return final_raw

    # ═══════════════════════════════════════════════════════════
    # Docker 工具集成
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _catalog_tool_filter(role_value: str, item=None) -> tuple[bool, list[str] | None]:
        """角色目錄 ∩ L3 原子白名單。空列表 = 不額外限制（除非原子角色指定）。"""
        from backend.company.role_catalog import resolve_runtime

        runtime = resolve_runtime(role_value)
        if runtime.get("allow_tool_use") is False:
            return False, None
        allowed = [str(row).strip() for row in (runtime.get("tools_allowed") or []) if str(row).strip()]
        atomic_tools: list[str] = []
        if item is not None:
            artifacts = getattr(item, "artifacts", None) or {}
            atomic = artifacts.get("atomic_role") if isinstance(artifacts, dict) else {}
            raw = []
            if isinstance(atomic, dict):
                raw = list(atomic.get("allowed_tools") or [])
            if not raw and isinstance(artifacts, dict):
                raw = list(artifacts.get("allowed_tools") or [])
            atomic_tools = [str(t).strip() for t in raw if str(t).strip()]
        if atomic_tools:
            if allowed:
                merged = [t for t in allowed if t in atomic_tools]
                return True, merged or atomic_tools
            return True, atomic_tools
        return True, (allowed or None)

    def _get_docker_tools_for_role(self, role_type: RoleType, item=None) -> str:
        """獲取角色可用的工具說明文字（使用新工具註冊表）。

        包含 Docker、記憶、實驗室等該角色可用的工具。
        若角色無可用工具或已停用工具，回傳空字串。
        """
        allow_tools, catalog_allowed = self._catalog_tool_filter(role_type.value, item)
        if not allow_tools:
            return ""
        return tool_registry.format_tools_prompt(
            role_type.value, catalog_allowed=catalog_allowed
        )

    def execute_docker_request(self, tool_name: str, args: dict[str, Any] | None = None) -> str:
        """執行 Docker 工具請求（供外部調用）。

        Args:
            tool_name: 工具名稱
            args: 工具參數

        Returns:
            格式化結果字串
        """
        dm = self.docker or get_docker_manager()
        return execute_docker_tool(tool_name, args, manager=dm)

    def get_docker_status(self) -> dict[str, Any]:
        """獲取 Docker 狀態摘要（供 API 與 UI 使用）。"""
        dm = self.docker or get_docker_manager()
        return {
            "available": dm.available,
            "containers": dm.list_containers(),
            "health": dm.health_check() if dm.available else {"_error": "Docker 不可用"},
        }
