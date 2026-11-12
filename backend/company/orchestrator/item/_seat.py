"""工作項 mixin 子模組：席位 I/O 記錄、任務規格與工具權限判定。"""

from __future__ import annotations

import logging
from typing import Any

from backend.company.roles import RoleType

from .._base import OrchestratorBase

logger = logging.getLogger("backend.company.orchestrator.item")


class _ItemSeatMixin(OrchestratorBase):
    """席位 I/O 記錄、任務規格與工具權限判定。"""

    def _record_seat_io(
        self,
        seat: dict | None,
        item,
        role_value: str,
        *,
        prompt: str,
        system: str,
        model: str | None,
        response: str,
        step: int,
        llm_kwargs: dict | None = None,
        duration_ms: float | None = None,
        tool_steps: int = 0,
        final: bool = True,
        error: str = "",
        degraded: bool = False,
        cost_usd: float | None = None,
    ) -> None:
        """落一筆席位投遞軌跡（全文 prompt/system/response + 來源分解）。

        同時寫入 seat_io 倉（監察餵給）與 tracer（/tasks/{id}/trace）；
        任何失敗都不得影響公司主流程。
        """
        meta = seat or {}
        record = {
            "run_id": self._run_id or "",
            "task_id": self.task_id or "",
            "item_id": getattr(item, "id", "") or "",
            "title": getattr(item, "title", "") or "",
            "role": role_value,
            "role_label": meta.get("role_label") or "",
            "layer": meta.get("layer"),
            "layer_label": meta.get("layer_label") or "",
            "lane": meta.get("lane") or "",
            "kind": meta.get("kind") or "execute",
            "attempt": meta.get("attempt", 0),
            "step": step,
            "tool_steps": tool_steps,
            "final": final,
            "model": model or "",
            "tier": meta.get("tier") or "",
            "temperature": (llm_kwargs or {}).get("temperature", meta.get("temperature")),
            "prompt": prompt,
            "system": system,
            "response": response,
            "duration_ms": round(float(duration_ms), 1) if duration_ms is not None else None,
            "cost_usd": round(float(cost_usd), 6) if cost_usd is not None else None,
            "error": error,
            "degraded": degraded,
            "allowed_tools": meta.get("allowed_tools") or [],
            "input_ref": meta.get("input_ref"),
            "output_schema": meta.get("output_schema") or "",
            "success_criteria": meta.get("success_criteria") or "",
            "context_sources": meta.get("context_sources") or [],
        }
        try:
            from backend.company.seat_io import record_seat_io

            record_seat_io(record)
        except Exception:
            logger.debug("席位 I/O 軌跡記錄異常（已忽略）", exc_info=True)
        try:
            if self.tracer is not None:
                self.tracer.log_llm_call(
                    prompt,
                    response,
                    model=model,
                    system=system,
                    duration_ms=duration_ms,
                    phase=str(meta.get("phase") or "execute"),
                    role=role_value,
                    item_id=str(record["item_id"]),
                    iteration=int(meta.get("attempt") or 0),
                )
        except Exception:
            logger.debug("席位 LLM 調用寫入 trace 異常（已忽略）", exc_info=True)

    def _seat_meta(
        self,
        role_type: RoleType,
        *,
        kind: str,
        phase: str,
        role_label: str = "",
        attempt: int = 0,
    ) -> dict[str, Any]:
        """非執行席位（審查／整合／終審）的投遞脈絡，無工具閉環故無來源分解。"""
        meta: dict[str, Any] = {
            "kind": kind,
            "phase": phase,
            "attempt": attempt,
            "role_label": role_label,
        }
        try:
            from backend.company.raho.protocol import layer_label, role_to_raho_layer

            layer = int(role_to_raho_layer(role_type))
            meta["layer"] = layer
            meta["layer_label"] = layer_label(layer)
        except Exception:
            meta["layer"] = None
        return meta

    def _task_spec_from_item(self, item) -> dict[str, Any]:
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        layer = artifacts.get("task_layer")
        if isinstance(layer, dict) and layer:
            return layer
        atomic_raw = artifacts.get("atomic_role")
        atomic = atomic_raw if isinstance(atomic_raw, dict) else {}
        inner = atomic.get("task_layer")
        if isinstance(inner, dict) and inner:
            return inner
        return {
            "task_description": item.description or item.title,
            "input_ref": artifacts.get("input_ref"),
            "allowed_tools": artifacts.get("allowed_tools") or [],
            "success_criteria": artifacts.get("success_criteria") or "",
            "output_schema": artifacts.get("output_schema") or "",
        }

    def _allowed_tools_for(self, item) -> list[str] | None:
        artifacts = item.artifacts if isinstance(getattr(item, "artifacts", None), dict) else {}
        tools = artifacts.get("allowed_tools")
        if isinstance(tools, list) and tools:
            return [str(t) for t in tools]
        atomic = artifacts.get("atomic_role") if isinstance(artifacts.get("atomic_role"), dict) else {}
        nested = atomic.get("allowed_tools") if isinstance(atomic, dict) else None
        if isinstance(nested, list) and nested:
            return [str(t) for t in nested]
        blob = f"{getattr(item, 'title', '')}\n{getattr(item, 'description', '')}"
        try:
            from backend.services.commander import fill_allowed_tools

            inferred = fill_allowed_tools(blob)
        except Exception:
            inferred = []
        if inferred:
            artifacts["allowed_tools"] = list(inferred)
            if isinstance(atomic, dict):
                atomic["allowed_tools"] = list(inferred)
                layer = atomic.get("task_layer")
                if isinstance(layer, dict):
                    layer["allowed_tools"] = list(inferred)
            return inferred
        return None
