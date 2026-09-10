"""多方智能路由：動態權重、跨廠商 Failover、競速。禁止 import 廠商 SDK。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from backend.hub.catalog import (
    AGENT_FALLBACK,
    CN_CHAIN,
    CN_SET,
    COST_PREFERRED,
    DEFAULT_CHAIN,
    DEFAULT_LATENCY_MS,
    INTEL,
    PRICE_PER_1M,
    QUALITY_FLAGSHIP,
    RACE_PAIR,
    provider_of,
)

CONNECT_TIMEOUT_S = 25.0
READ_TIMEOUT_S = 120.0
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


class CircuitOpenError(Exception):
    """熔斷器開啟，不得對該模型發請求。"""


class HubUpstreamError(Exception):
    """上游可分類錯誤（測試與適配層共用）。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Metrics:
    latency_ms: float
    price_out_per_1m: float


@dataclass
class RouteDecision:
    model: str
    provider: str
    score: float
    reason: str


def default_metrics(model: str) -> Metrics:
    _, out_price = PRICE_PER_1M[model]
    return Metrics(
        latency_ms=DEFAULT_LATENCY_MS.get(model, 800.0),
        price_out_per_1m=out_price,
    )


def score_model(model: str, metrics: Metrics, strategy: str) -> float:
    w_intel = {"quality_first": 1.00, "cost_first": 0.25, "speed_first": 0.40}[strategy]
    lat_coef = 0.008 if strategy == "speed_first" else 0.001
    price_coef = 2.0 if strategy == "cost_first" else 0.5
    return (
        INTEL[model] * w_intel
        - metrics.latency_ms * lat_coef
        - metrics.price_out_per_1m * price_coef
    )


def filter_by_region(models: Iterable[str], region: str) -> list[str]:
    models = list(models)
    if region.upper() == "CN":
        return [m for m in models if m in CN_SET]
    return models


def pick_primary(
    strategy: str,
    region: str,
    whitelist: list[str] | None,
    metrics_by_model: dict[str, Metrics],
    manual_model: str | None,
    circuit_open: Callable[[str], bool] | None = None,
) -> RouteDecision:
    if strategy == "manual":
        if not manual_model:
            raise ValueError("MANUAL_MODEL_REQUIRED")
        allowed = filter_by_region([manual_model], region)
        if not allowed:
            raise PermissionError("DATA_EGRESS_FORBIDDEN")
        return RouteDecision(manual_model, provider_of(manual_model), float("nan"), "manual")

    pool = list(whitelist or INTEL.keys())
    pool = [m for m in pool if m in INTEL]
    pool = filter_by_region(pool, region)
    if not pool:
        raise PermissionError("DATA_EGRESS_FORBIDDEN")
    if circuit_open:
        healthy = [m for m in pool if not circuit_open(m)]
        if healthy:
            pool = healthy

    ranked: list[RouteDecision] = []
    for m in pool:
        known = m in metrics_by_model
        met = metrics_by_model.get(m) or default_metrics(m)
        s = score_model(m, met, strategy)
        if not known:
            s -= 5.0
        ranked.append(RouteDecision(m, provider_of(m), s, "weighted"))
    ranked.sort(key=lambda d: d.score, reverse=True)

    # quality_first 額外規則：旗艦健康時鎖定 GPT-5.6 Sol（HUB-R2）
    if strategy == "quality_first":
        for d in ranked:
            if d.model == QUALITY_FLAGSHIP:
                return RouteDecision(d.model, d.provider, d.score, "quality_flagship")

    # cost_first 額外規則：候選含 DeepSeek 時優先（§6.4）
    if strategy == "cost_first":
        for d in ranked:
            if d.model == COST_PREFERRED:
                return RouteDecision(d.model, d.provider, d.score, "cost_preferred")

    return ranked[0]


def backoff_sleep(attempt: int, rng: random.Random | None = None) -> float:
    jitter = (rng or random).uniform(0.0, 0.2)
    return (BACKOFF_BASE ** attempt) + jitter


def failover_chain(primary: str, region: str, whitelist: list[str] | None) -> list[str]:
    if region.upper() == "CN":
        chain = list(CN_CHAIN)
    else:
        chain = list(DEFAULT_CHAIN)
        if primary in chain:
            chain.remove(primary)
        chain.insert(0, primary)
        if primary == QUALITY_FLAGSHIP and AGENT_FALLBACK not in chain:
            # Agent 二次呼叫降級契約：Sol → Qwen3.5-Max 仍可經白名單插入
            pass
    if whitelist:
        allowed = set(whitelist)
        chain = [m for m in chain if m in allowed]
    return chain


def agent_synthesis_chain(region: str, whitelist: list[str] | None) -> list[str]:
    """金融場景二次生成：GPT-5.6 Sol，限流則 Qwen3.5-Max。"""
    if region.upper() == "CN":
        chain = ["qwen3.5-max", "deepseek-v4-flash", "mimo-v2.5-pro"]
    else:
        chain = [QUALITY_FLAGSHIP, AGENT_FALLBACK]
    if whitelist:
        chain = [m for m in chain if m in set(whitelist)]
    return chain


def should_switch(exc: BaseException, status_code: int | None) -> bool:
    if status_code in {429, 503}:
        return True
    name = type(exc).__name__
    if name in {"TimeoutError", "ConnectTimeout", "ReadTimeout", "CircuitOpenError"}:
        return True
    text = str(exc).lower()
    return "429" in text or "503" in text or "rate" in text or "timeout" in text


def invoke_with_failover(
    call_llm: Callable[..., str],
    messages: list[dict],
    primary: str,
    region: str,
    whitelist: list[str] | None,
    connect_s: float = CONNECT_TIMEOUT_S,
    read_s: float = READ_TIMEOUT_S,
    sleeper: Callable[[float], None] | None = None,
    chain: list[str] | None = None,
    circuit_open: Callable[[str], bool] | None = None,
    on_result: Callable[[str, bool, float], None] | None = None,
) -> tuple[str, str, int]:
    """回傳 (text, model, hops)。hops=切換次數。熔斷 Open 的模型直接跳過。"""
    hops = 0
    last_err: Exception | None = None
    sleep = sleeper or time.sleep
    models = chain if chain is not None else failover_chain(primary, region, whitelist)
    user_prompt, system = _split_messages(messages)

    for model in models:
        if circuit_open and circuit_open(model):
            hops += 1
            last_err = CircuitOpenError(model)
            continue
        for attempt in range(MAX_RETRIES + 1):
            t0 = time.monotonic()
            try:
                text = call_llm(
                    prompt=user_prompt,
                    system=system,
                    model=model,
                    max_retries=1,
                    timeout=connect_s + read_s,
                )
                if on_result:
                    on_result(model, False, time.monotonic() - t0)
                return text, model, hops
            except Exception as exc:
                last_err = exc
                status = getattr(exc, "status_code", None)
                timed_out = (time.monotonic() - t0) > read_s
                if on_result:
                    on_result(model, True, time.monotonic() - t0)
                if timed_out or should_switch(exc, status):
                    if attempt < MAX_RETRIES and status not in {429, 503}:
                        sleep(backoff_sleep(attempt))
                        continue
                    hops += 1
                    break
                if attempt < MAX_RETRIES:
                    sleep(backoff_sleep(attempt))
                    continue
                hops += 1
                break
    timeout_like = last_err is not None and (
        isinstance(last_err, (TimeoutError, CircuitOpenError))
        or "timeout" in str(last_err).lower()
    )
    if timeout_like and not isinstance(last_err, CircuitOpenError):
        raise TimeoutError("UPSTREAM_TIMEOUT") from last_err
    raise HubUpstreamError("ALL_PROVIDERS_UNAVAILABLE", status_code=503) from last_err


def _split_messages(messages: list[dict]) -> tuple[str, str | None]:
    systems = [
        str(m.get("content") or "")
        for m in messages
        if m.get("role") == "system" and isinstance(m.get("content"), str)
    ]
    users = [
        str(m.get("content") or "")
        for m in messages
        if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    assistants = [
        f"{m.get('role')}: {m.get('content')}"
        for m in messages
        if m.get("role") in {"assistant", "tool"} and isinstance(m.get("content"), str)
    ]
    prompt_parts = assistants + users
    prompt = prompt_parts[-1] if prompt_parts else ""
    if len(prompt_parts) > 1:
        prompt = "\n".join(prompt_parts)
    system = "\n".join(systems) if systems else None
    return prompt, system


def _is_valid_sse_first_byte(first: bytes) -> bool:
    if not first or first.startswith(b":"):
        return False
    text = first.decode("utf-8", errors="replace")
    return "data:" in text and "content" in text


async def race_to_the_top(
    stream_factory: Callable[[str], AsyncIterator[bytes]],
    ttfb_deadline_ms: int = 200,
) -> tuple[str, bytes]:
    models = RACE_PAIR
    loop = asyncio.get_running_loop()
    winner: asyncio.Future = loop.create_future()
    tasks: list[asyncio.Task] = []

    async def run(model: str) -> None:
        agen = stream_factory(model)
        t0 = time.monotonic()
        try:
            first = await asyncio.wait_for(agen.__anext__(), timeout=2.0)
        except Exception:
            return
        ttfb_ms = (time.monotonic() - t0) * 1000
        if not _is_valid_sse_first_byte(first):
            return
        if not winner.done():
            winner.set_result((model, first, ttfb_ms, agen))

    for m in models:
        tasks.append(asyncio.create_task(run(m)))

    pending: set[asyncio.Future] = {winner, *tasks}
    await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    if not winner.done():
        await asyncio.wait(pending, timeout=2.0)
    if not winner.done():
        for t in tasks:
            t.cancel()
        raise TimeoutError("RACE_NO_VALID_TTFB")

    model, first, ttfb_ms, _agen = winner.result()
    for t in tasks:
        t.cancel()
    _ = ttfb_deadline_ms
    _ = ttfb_ms
    return model, first


def race_sync(
    call_llm: Callable[..., str],
    messages: list[dict],
    ttfb_deadline_ms: int = 200,
) -> tuple[str, str]:
    """同步競速：同時打 Gemini 3.1 Pro 與 Mercury 2，先回有效內容者勝。"""
    user_prompt, system = _split_messages(messages)
    winner: dict[str, Any] = {}
    lock = threading.Lock()

    def run(model: str) -> None:
        try:
            text = call_llm(
                prompt=user_prompt,
                system=system,
                model=model,
                max_retries=1,
                timeout=2.0,
            )
        except Exception:
            return
        if not text or not str(text).strip():
            return
        with lock:
            if "model" not in winner:
                winner["model"] = model
                winner["text"] = str(text)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(run, m) for m in RACE_PAIR]
        concurrent.futures.wait(futs, timeout=2.0, return_when=concurrent.futures.FIRST_COMPLETED)
        if "model" not in winner:
            concurrent.futures.wait(futs, timeout=2.0)
    if "model" not in winner:
        raise TimeoutError("RACE_NO_VALID_TTFB")
    _ = ttfb_deadline_ms
    return winner["model"], winner["text"]
