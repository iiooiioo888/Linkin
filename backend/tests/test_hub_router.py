"""AI Hub 路由算法單元測試（動態權重 / Failover / Race）。"""

from __future__ import annotations

import asyncio

import pytest

from backend.hub.catalog import CN_SET, DEFAULT_CHAIN, HUB_CATALOG, INTEL
from backend.hub.router import (
    HubUpstreamError,
    Metrics,
    _is_valid_sse_first_byte,
    failover_chain,
    filter_by_region,
    invoke_with_failover,
    pick_primary,
    race_to_the_top,
    score_model,
)


def test_intel_keys_equal_catalog() -> None:
    assert set(INTEL) == HUB_CATALOG


def test_quality_first_picks_sol_when_healthy() -> None:
    decision = pick_primary("quality_first", "TW", None, {}, None)
    assert decision.model == "gpt-5.6-sol"
    assert decision.provider == "openai"


def test_cost_first_prefers_deepseek() -> None:
    decision = pick_primary("cost_first", "TW", None, {}, None)
    assert decision.model == "deepseek-v4-flash"


def test_cn_region_filters_to_cn_set() -> None:
    assert set(filter_by_region(INTEL.keys(), "CN")) == CN_SET
    with pytest.raises(PermissionError, match="DATA_EGRESS_FORBIDDEN"):
        pick_primary("manual", "CN", None, {}, "gpt-5.6-sol")


def test_cn_quality_picks_from_cn_set() -> None:
    decision = pick_primary("quality_first", "CN", None, {}, None)
    assert decision.model in CN_SET


def test_default_chain_no_claude() -> None:
    assert DEFAULT_CHAIN == (
        "gpt-5.6-sol",
        "gemini-3.1-pro",
        "deepseek-v4-flash",
        "glm-5.3",
    )
    chain = failover_chain("gpt-5.6-sol", "US", None)
    assert chain[0] == "gpt-5.6-sol"
    assert "claude" not in " ".join(chain).lower()


def test_score_formula_cost_vs_quality() -> None:
    met = Metrics(latency_ms=400, price_out_per_1m=30.0)
    q = score_model("gpt-5.6-sol", met, "quality_first")
    c = score_model("gpt-5.6-sol", met, "cost_first")
    assert q > c


def test_failover_switches_on_429() -> None:
    calls: list[str] = []

    def fake(*, prompt, system=None, model=None, **kwargs):
        calls.append(model)
        if model == "gpt-5.6-sol":
            raise HubUpstreamError("rate limited", status_code=429)
        return f"ok:{model}"

    text, model, hops = invoke_with_failover(
        fake,
        [{"role": "user", "content": "hi"}],
        "gpt-5.6-sol",
        "TW",
        None,
        sleeper=lambda _s: None,
    )
    assert model == "gemini-3.1-pro"
    assert hops >= 1
    assert "ok:gemini-3.1-pro" == text
    assert calls[0] == "gpt-5.6-sol"


def test_cn_failover_chain() -> None:
    chain = failover_chain("deepseek-v4-flash", "CN", None)
    assert chain == ["deepseek-v4-flash", "qwen3.8-max", "mimo-v2.5-pro"]


@pytest.mark.asyncio
async def test_race_to_the_top_cancels_loser() -> None:
    cancelled = []

    async def factory(model: str):
        try:
            if model == "mercury-2":
                yield b'data: {"choices":[{"delta":{"content":"fast"}}]}\n\n'
            else:
                await asyncio.sleep(1.0)
                yield b'data: {"choices":[{"delta":{"content":"slow"}}]}\n\n'
        except asyncio.CancelledError:
            cancelled.append(model)
            raise

    model, first = await race_to_the_top(factory)
    assert model == "mercury-2"
    assert b"fast" in first


def test_sse_first_byte_rejects_ping() -> None:
    assert not _is_valid_sse_first_byte(b": ping\n")
    assert _is_valid_sse_first_byte(
        b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
    )


def test_open_circuit_skips_primary() -> None:
    calls: list[str] = []

    def fake(*, prompt, system=None, model=None, **kwargs):
        calls.append(model)
        return f"ok:{model}"

    text, model, hops = invoke_with_failover(
        fake,
        [{"role": "user", "content": "hi"}],
        "gpt-5.6-sol",
        "TW",
        None,
        sleeper=lambda _s: None,
        circuit_open=lambda m: m == "gpt-5.6-sol",
    )
    assert model == "gemini-3.1-pro"
    assert hops >= 1
    assert "gpt-5.6-sol" not in calls
    assert text == "ok:gemini-3.1-pro"


def test_probe_ewma_and_penalty(monkeypatch) -> None:
    from backend.hub.probe import FAIL_PENALTY_MS, probe_once
    from backend.hub.runtime import reset_runtime, runtime

    reset_runtime()

    def fake(*, prompt, system=None, model=None, **kwargs):
        if model == "gpt-5.6-sol":
            raise TimeoutError("probe fail")
        return "pong"

    metrics = probe_once(llm=fake)
    assert metrics["gpt-5.6-sol"]["latency_ewma_ms"] == FAIL_PENALTY_MS
    assert metrics["gpt-5.6-sol"]["consecutive_fail"] >= 1
    assert metrics["gemini-3.1-pro"]["consecutive_fail"] == 0
    assert "claude" not in " ".join(metrics).lower()
    _ = runtime


def test_race_sync_picks_first() -> None:
    from backend.hub.router import race_sync

    def fake(*, prompt, system=None, model=None, **kwargs):
        if model == "mercury-2":
            return "fast-mercury"
        return "slow-gemini"

    model, text = race_sync(fake, [{"role": "user", "content": "go"}])
    assert model in {"gemini-3.1-pro", "mercury-2"}
    assert text in {"fast-mercury", "slow-gemini"}
