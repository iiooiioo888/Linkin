"""選路 + Failover（Open 態跳過；本地→雲形狀預留）。不含 CN egress／race。"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from backend.modelgw.admission import AdmissionPolicy, admit
from backend.modelgw.circuit import CircuitRegistry
from backend.modelgw.errors import (
    CODE_ALL_OPEN,
    CODE_UPSTREAM,
    ModelGWError,
)
from backend.modelgw.registry import Registry


@dataclass
class RouteHop:
    model_id: str
    plane: str
    reason: str


@dataclass
class RoutePlan:
    primary: str
    chain: list[str]
    hops_skipped_open: list[str]


def build_failover_chain(
    primary: str,
    registry: Registry,
    *,
    extras: Sequence[str] | None = None,
) -> list[str]:
    """主模型 + extras + 其餘 READY（local 優先於 cloud），去重保序。"""
    seen: set[str] = set()
    chain: list[str] = []

    def add(mid: str) -> None:
        if mid and mid not in seen:
            seen.add(mid)
            chain.append(mid)

    add(primary)
    for mid in extras or ():
        add(mid)

    ready = registry.ready()
    locals_ = sorted((r for r in ready if r.plane == "local"), key=lambda r: r.model_id)
    clouds = sorted((r for r in ready if r.plane != "local"), key=lambda r: r.model_id)
    for r in locals_ + clouds:
        add(r.model_id)
    return chain


def plan_route(
    primary: str,
    registry: Registry,
    circuits: CircuitRegistry,
    *,
    extras: Sequence[str] | None = None,
    policy: AdmissionPolicy | None = None,
) -> RoutePlan:
    """僅納入準入通過且電路未 OPEN 的候選；主模型 OPEN 則跳過並 Failover。"""
    raw = build_failover_chain(primary, registry, extras=extras)
    admitted: list[str] = []
    skipped_open: list[str] = []
    for mid in raw:
        result = admit(mid, registry, policy)
        if not result.allowed:
            continue
        if circuits.is_open(mid):
            skipped_open.append(mid)
            continue
        admitted.append(mid)
    if not admitted:
        raise ModelGWError(
            CODE_ALL_OPEN,
            "所有候選電路開啟或未準入",
            http_hint=503,
        )
    return RoutePlan(primary=admitted[0], chain=admitted, hops_skipped_open=skipped_open)


def invoke_with_failover(
    llm: Callable[..., str],
    messages: list[dict[str, Any]],
    plan: RoutePlan,
    circuits: CircuitRegistry,
    *,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[str, str, int]:
    """依 plan.chain 呼叫；失敗記電路並跳下一跳。回傳 (text, used_model, hops)。"""
    _ = sleeper  # 預留退避
    prompt = ""
    for m in messages:
        if m.get("role") == "user":
            prompt = str(m.get("content") or "")
            break
    last_err: Exception | None = None
    hops = 0
    for mid in plan.chain:
        if circuits.is_open(mid):
            continue
        hops += 1
        t0 = time.monotonic()
        try:
            text = llm(prompt=prompt, model=mid, messages=messages)
            circuits.get(mid).record(failed=False, duration_s=time.monotonic() - t0)
            return text, mid, max(0, hops - 1)
        except Exception as exc:
            last_err = exc
            circuits.get(mid).record(failed=True, duration_s=time.monotonic() - t0)
    raise ModelGWError(
        CODE_UPSTREAM,
        f"Failover 耗盡：{last_err}",
        http_hint=502,
    )
