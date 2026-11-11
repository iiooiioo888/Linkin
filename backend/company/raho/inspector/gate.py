"""InspectorGate 閘門（自 backend.company.raho.inspector 抽出）。

L1 審查閘門：規則優先、可選 LLM、簽核路由與例外拋出。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from backend.company.raho.atomic_executor import AtomicTaskSpec

from .constants import (
    CONSTITUTION_LAYER,
    INSPECTOR_MARKER,
    VERDICT_APPROVED,
    VERDICT_ESCALATE,
    VERDICT_REWORK,
)
from .models import EscalateRequired, InspectorVerdict, ReworkRequired
from .service import (
    compose_inspector_prompt,
    l1_llm_enabled,
    parse_verdict,
    run_inspection,
    write_signed_memory,
)
from .similarity import _as_text


class InspectorGate:
    """L1 審查閘門：組裝憲法層 Prompt、規則驗收、可選 LLM、簽核路由。"""

    CONSTITUTION_LAYER = CONSTITUTION_LAYER
    INSPECTOR_MARKER = INSPECTOR_MARKER

    def __init__(self, llm: Callable[..., str] | None = None):
        self.system_prompt = CONSTITUTION_LAYER
        self.llm = llm

    @classmethod
    def spawn(cls, task_spec: dict[str, Any] | AtomicTaskSpec, l2_output: str, *, source_preview: str = "") -> str:
        """輸入 L3 規格 + L2 產出，輸出完整 L1 System Prompt（憲法層唯讀）。"""
        return compose_inspector_prompt(task_spec, l2_output, source_preview=source_preview)

    def compose(self, task_spec: dict[str, Any] | AtomicTaskSpec, l2_output: str, *, source_preview: str = "") -> str:
        return self.spawn(task_spec, l2_output, source_preview=source_preview)

    def inspect(
        self,
        task_spec: dict[str, Any] | AtomicTaskSpec,
        l2_output: str,
        *,
        source_data: Any = None,
        rework_rounds: int = 0,
        max_rework: int = 2,
        node_id: str = "",
        title: str = "",
        use_llm: bool | None = None,
    ) -> InspectorVerdict:
        """規則優先；僅在環境開啟且規則無法決時才呼叫 LLM。"""
        verdict = run_inspection(
            task_spec,
            l2_output,
            source_data=source_data,
            rework_rounds=rework_rounds,
            max_rework=max_rework,
            node_id=node_id,
        )
        want_llm = l1_llm_enabled() if use_llm is None else use_llm
        if want_llm and verdict.verdict == VERDICT_APPROVED:
            llm_verdict = self._llm_inspect(task_spec, l2_output, source_data)
            if llm_verdict is not None and llm_verdict.verdict != VERDICT_APPROVED:
                verdict = llm_verdict
        try:
            from backend.company.raho.l0 import apply_radar_bias

            verdict = apply_radar_bias(verdict)
        except Exception:
            pass
        if verdict.verdict == VERDICT_APPROVED:
            write_signed_memory(node_id or verdict.node_id, verdict, title=title)
        return verdict

    def inspect_or_raise(self, *args: Any, **kwargs: Any) -> InspectorVerdict:
        verdict = self.inspect(*args, **kwargs)
        if verdict.verdict == VERDICT_REWORK:
            raise ReworkRequired(verdict)
        if verdict.verdict == VERDICT_ESCALATE:
            raise EscalateRequired(verdict)
        return verdict

    def _llm_inspect(
        self,
        task_spec: dict[str, Any] | AtomicTaskSpec,
        l2_output: str,
        source_data: Any,
    ) -> InspectorVerdict | None:
        prompt = self.compose(task_spec, l2_output, source_preview=_as_text(source_data)[:2000])
        started = time.monotonic()
        try:
            if self.llm is not None:
                raw = self.llm(prompt)
            else:
                from backend.core.llm import call_llm

                raw = call_llm(prompt, system=self.system_prompt)
        except Exception:
            return None
        try:
            from backend.company.raho.protocol import RahoLayer, layer_label
            from backend.company.seat_io import record_seat_io

            spec = task_spec if isinstance(task_spec, dict) else getattr(task_spec, "__dict__", {})
            record_seat_io({
                "item_id": str(spec.get("node_id") or spec.get("item_id") or ""),
                "title": str(spec.get("title") or "")[:80],
                "role": "constitutional_inspector",
                "role_label": "L1 憲兵（獨立審查）",
                "layer": int(RahoLayer.L1_INSPECTOR),
                "layer_label": layer_label(int(RahoLayer.L1_INSPECTOR)),
                "lane": "inspect",
                "kind": "inspect",
                "system": self.system_prompt,
                "prompt": prompt,
                "response": raw,
                "duration_ms": round((time.monotonic() - started) * 1000.0, 1),
                "context_sources": [
                    {"kind": "constitution", "label": "憲法層唯讀區塊（L3 規格＋L2 產出動態注入）", "text": self.system_prompt},
                    {"kind": "deliverable", "label": "被審查的 L2 產出", "text": _as_text(l2_output)[:4000]},
                ],
            })
        except Exception:
            pass
        return parse_verdict(raw)
