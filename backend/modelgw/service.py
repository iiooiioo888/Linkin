"""ModelGW 單入口（純庫）：admit → route → invoke。不掛 FastAPI／LiteLLM。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from backend.modelgw.admission import AdmissionPolicy, AdmitDecision, admit
from backend.modelgw.circuit import CircuitRegistry
from backend.modelgw.errors import (
    CODE_ADMISSION,
    CODE_NOT_READY,
    CODE_PROVISIONING,
    CODE_UNSUPPORTED,
    ModelGWError,
)
from backend.modelgw.registry import InMemoryRegistry, Registry
from backend.modelgw.router import invoke_with_failover, plan_route


@dataclass
class InvokeResult:
    text: str
    model_id: str
    failover_hops: int
    skipped_open: list[str]


class ModelGWService:
    def __init__(
        self,
        registry: Registry | None = None,
        circuits: CircuitRegistry | None = None,
        policy: AdmissionPolicy | None = None,
        metrics: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.registry: Registry = registry or InMemoryRegistry()
        self.circuits = circuits or CircuitRegistry()
        self.policy = policy or AdmissionPolicy()
        self.metrics: dict[str, dict[str, Any]] = metrics if metrics is not None else {}

    def admit_or_raise(self, model_id: str):
        result = admit(model_id, self.registry, self.policy)
        if result.decision == AdmitDecision.PROVISIONING:
            raise ModelGWError(
                CODE_PROVISIONING,
                f"模型 {model_id} 部署中，暫不路由",
                http_hint=503,
            )
        if result.decision == AdmitDecision.REJECT:
            code = result.code or CODE_ADMISSION
            hint = 400
            raise ModelGWError(
                code,
                f"準入拒絕：{model_id} ({result.reason or code})",
                reason=result.reason,
                http_hint=hint,
            )
        return result

    def route(
        self,
        model_id: str,
        *,
        extras: Sequence[str] | None = None,
    ):
        """準入主模型後產出 Failover 計畫（Open 跳過）。"""
        self.admit_or_raise(model_id)
        return plan_route(
            model_id,
            self.registry,
            self.circuits,
            extras=extras,
            policy=self.policy,
        )

    def invoke_chat(
        self,
        model_id: str,
        messages: list[dict[str, Any]],
        llm: Callable[..., str],
        *,
        extras: Sequence[str] | None = None,
    ) -> InvokeResult:
        """完整熱路徑：準入 → 選路 → 呼叫（mock／注入 llm）。"""
        plan = self.route(model_id, extras=extras)
        text, used, hops = invoke_with_failover(
            llm,
            messages,
            plan,
            self.circuits,
        )
        return InvokeResult(
            text=text,
            model_id=used,
            failover_hops=hops,
            skipped_open=list(plan.hops_skipped_open),
        )


# 重新匯出錯誤碼，方便測試 import
__all__ = [
    "CODE_ADMISSION",
    "CODE_NOT_READY",
    "CODE_PROVISIONING",
    "CODE_UNSUPPORTED",
    "InvokeResult",
    "ModelGWService",
]
