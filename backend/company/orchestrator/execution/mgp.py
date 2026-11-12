"""MGP 裁決修補 mixin：質詢裁決解析、重試執行與工作項修補。"""

from __future__ import annotations

import asyncio
import logging

from backend.company.events import CompanyEvent
from backend.company.roles import RoleType

from .._base import OrchestratorBase

logger = logging.getLogger("backend.company.orchestrator.execution")


class _ExecutionMgpMixin(OrchestratorBase):
    """MGP 裁決解析／重試執行與升級修補。"""

    async def _maybe_resolve_mgp(
        self,
        goal: str,
        item,
        role_type: RoleType,
        raw: str,
        prompt: str,
        system_prompt: str,
        model: str,
        llm_opts: dict | None,
        timeout_s: float,
        seat: dict | None = None,
    ) -> tuple[str, str]:
        """若產出含 [GRILL]，走熱馬桶圈後重試一次執行。無標記則原樣返回。"""
        try:
            from backend.company.raho.escalation import resolve_grill
            from backend.company.raho.mgp import (
                parse_choices,
                parse_grill_output,
                strip_protocol_marks,
            )
            from backend.company.raho.protocol import mgp_enabled
        except Exception:
            return raw, prompt
        if not mgp_enabled():
            return raw, prompt
        kind, issues = parse_grill_output(raw)
        if kind == "clear":
            return raw, prompt
        extra_choices = parse_choices(raw) if kind == "escalate" else []
        self.events.emit(CompanyEvent.GRILL_RAISED, {
            "item_id": item.id,
            "title": item.title,
            "role": role_type.value,
            "issues": [i.to_dict() for i in issues],
        })
        resolved = await resolve_grill(
            run_id=self._run_id or item.id,
            item_id=item.id,
            goal=goal,
            title=item.title,
            description=item.description,
            issues=issues,
            assignee=role_type.value,
            choices=extra_choices or None,
            superior="manager",
            allowed_tools=self._allowed_tools_for(item),
            on_user_pending=lambda p: self._emit_user_pending(p, title=item.title),
        )
        self._apply_escalation_patch(item, resolved)
        reply = str(resolved.get("reply") or "").strip()
        self.events.emit(CompanyEvent.GRILL_RESOLVED, {
            "item_id": item.id,
            "layer": resolved.get("layer"),
            "action": resolved.get("action"),
            "timeout": bool(resolved.get("timeout")),
        })
        if resolved.get("timeout"):
            self.events.emit(CompanyEvent.RAHO_TIMEOUT, {
                "item_id": item.id, "choice": resolved.get("choice"),
            })
        if not reply:
            return strip_protocol_marks(raw) or raw, prompt
        next_prompt = prompt + f"\n\n【上級對質詢的裁決】\n{reply}\n請依裁決產出交付物，不要再重複質詢。"
        if isinstance(seat, dict):
            seat["context_sources"] = list(seat.get("context_sources") or []) + [{
                "kind": "grill_ruling",
                "label": f"產後質詢裁決（上級 layer={resolved.get('layer')}）",
                "text": reply,
            }]
        try:
            if timeout_s > 0:
                retried = await asyncio.wait_for(
                    self._execute_with_tool_loop(
                        next_prompt, system_prompt, model, role_type.value, item,
                        llm_kwargs=llm_opts, seat=seat,
                    ),
                    timeout=timeout_s,
                )
            else:
                retried = await self._execute_with_tool_loop(
                    next_prompt, system_prompt, model, role_type.value, item,
                    llm_kwargs=llm_opts, seat=seat,
                )
            kind2, _ = parse_grill_output(retried)
            if kind2 == "clear":
                return retried, next_prompt
            return strip_protocol_marks(retried) or reply, next_prompt
        except Exception as exc:
            logger.warning("MGP 重試執行失敗，使用裁決原文：%s", exc)
            return reply, next_prompt

    def _apply_escalation_patch(self, item, resolved: dict) -> None:
        """把 L3 SOP 重發的工具／預算寫回原子工作項。"""
        if not isinstance(resolved, dict) or not item:
            return
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        atomic = artifacts.get("atomic_role") if isinstance(artifacts.get("atomic_role"), dict) else {}
        tools = resolved.get("reissued_tools")
        if isinstance(tools, list) and tools:
            artifacts["allowed_tools"] = list(tools)
            if atomic:
                atomic["allowed_tools"] = list(tools)
                layer = atomic.get("task_layer")
                if isinstance(layer, dict):
                    layer["allowed_tools"] = list(tools)
        budget = resolved.get("reissued_budget")
        if isinstance(budget, dict):
            if budget.get("max_iterations") is not None:
                artifacts["max_iterations"] = budget["max_iterations"]
                if atomic:
                    atomic["max_iterations"] = budget["max_iterations"]
            if budget.get("token_budget") is not None:
                artifacts["token_budget"] = budget["token_budget"]
                if atomic:
                    atomic["token_budget"] = budget["token_budget"]
