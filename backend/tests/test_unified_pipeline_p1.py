"""P1：路由前共用前置增強（OPC／靈境／整合召回並行 + 逾時降級）。

對應設計 `docs/design/roadmap-1-unified-pipeline.md` §3.4（`pre` 階段）、
§7.4(b)（並行 + 300ms 逾時降級）與 §6.1 Q8（degraded 可見性）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.core.unified_pipeline import (
    DEFAULT_PRE_ENHANCE_TIMEOUT_MS,
    pre_enhance_timeout_ms,
    run_pre_route_enhancements,
)

OPC_MOD = "backend.core.company_nodes.enhance_with_opc_context"
LINKIN_MOD = "backend.linkin.pipeline.enhance_with_linkin_context"
RECALL_MOD = "backend.integrations.recall_bridge.enhance_with_recall_context"


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    monkeypatch.delenv("EVOL_PRE_ENHANCE_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("EVOL_UNIFIED_PIPELINE", raising=False)
    from backend.core.cost_speed_router import reload_cost_speed

    reload_cost_speed()
    yield
    reload_cost_speed()


# ── 逾時預算解析 ─────────────────────────────────────────────


class TestPreEnhanceTimeout:
    def test_default_from_shipped_config(self):
        assert pre_enhance_timeout_ms() == DEFAULT_PRE_ENHANCE_TIMEOUT_MS

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("EVOL_PRE_ENHANCE_TIMEOUT_MS", "750")
        assert pre_enhance_timeout_ms() == 750

    def test_config_value_used_when_no_env(self, monkeypatch, tmp_path):
        cfg = tmp_path / "cost_speed.json"
        cfg.write_text(
            json.dumps({"unified_pipeline": {"pre_enhance_timeout_ms": 1234}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(cfg))
        from backend.core.cost_speed_router import reload_cost_speed

        reload_cost_speed()
        assert pre_enhance_timeout_ms() == 1234

    @pytest.mark.parametrize("bad", ["abc", "0", "-5"])
    def test_invalid_env_falls_back_to_config(self, monkeypatch, bad):
        monkeypatch.setenv("EVOL_PRE_ENHANCE_TIMEOUT_MS", bad)
        assert pre_enhance_timeout_ms() == DEFAULT_PRE_ENHANCE_TIMEOUT_MS


# ── 並行增強與降級 ───────────────────────────────────────────


class TestRunPreRouteEnhancements:
    @pytest.mark.asyncio
    async def test_all_sources_fast_merges_and_no_degradation(self):
        async def opc(_state):
            return {"opc_context": {"opc_status": "available", "summary": "OPC"}}

        def linkin(_state):
            return {"linkin_context": {"summary": "LINKIN"}}

        def recall(_state):
            return {"recall_context": {"injection": "RECALL"}}

        with (
            patch(OPC_MOD, side_effect=opc),
            patch(LINKIN_MOD, side_effect=linkin),
            patch(RECALL_MOD, side_effect=recall),
        ):
            update, degraded = await run_pre_route_enhancements({"query": "q"}, timeout_ms=2000)

        assert update["opc_context"]["summary"] == "OPC"
        assert update["linkin_context"]["summary"] == "LINKIN"
        assert update["recall_context"]["injection"] == "RECALL"
        assert degraded == {"context_degraded": False, "degraded_sources": []}

    @pytest.mark.asyncio
    async def test_slow_source_degrades_without_blocking_fast_sources(self):
        async def slow_opc(_state):
            await asyncio.sleep(5)
            return {"opc_context": {"summary": "TOO-LATE"}}

        def linkin(_state):
            return {"linkin_context": {"summary": "LINKIN"}}

        def recall(_state):
            return {"recall_context": {"injection": "RECALL"}}

        with (
            patch(OPC_MOD, side_effect=slow_opc),
            patch(LINKIN_MOD, side_effect=linkin),
            patch(RECALL_MOD, side_effect=recall),
        ):
            update, degraded = await run_pre_route_enhancements({"query": "q"}, timeout_ms=50)

        # 快源結果照常併入；逾時慢源被取消並標記
        assert update["linkin_context"]["summary"] == "LINKIN"
        assert update["recall_context"]["injection"] == "RECALL"
        assert "opc_context" not in update
        assert degraded["context_degraded"] is True
        assert degraded["degraded_sources"] == ["opc"]

    @pytest.mark.asyncio
    async def test_raising_source_degrades_others_still_merge(self):
        async def bad_opc(_state):
            raise RuntimeError("opc boom")

        def linkin(_state):
            return {"linkin_context": {"summary": "LINKIN"}}

        def recall(_state):
            return {}

        with (
            patch(OPC_MOD, side_effect=bad_opc),
            patch(LINKIN_MOD, side_effect=linkin),
            patch(RECALL_MOD, side_effect=recall),
        ):
            update, degraded = await run_pre_route_enhancements({"query": "q"}, timeout_ms=2000)

        assert update["linkin_context"]["summary"] == "LINKIN"
        assert degraded["degraded_sources"] == ["opc"]

    @pytest.mark.asyncio
    async def test_timeout_budget_read_from_config(self, monkeypatch, tmp_path):
        cfg = tmp_path / "cost_speed.json"
        cfg.write_text(
            json.dumps({"unified_pipeline": {"pre_enhance_timeout_ms": 40}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(cfg))
        from backend.core.cost_speed_router import reload_cost_speed

        reload_cost_speed()

        async def slow_opc(_state):
            await asyncio.sleep(5)
            return {}

        def fast(_state):
            return {}

        with (
            patch(OPC_MOD, side_effect=slow_opc),
            patch(LINKIN_MOD, side_effect=fast),
            patch(RECALL_MOD, side_effect=fast),
        ):
            _update, degraded = await run_pre_route_enhancements({"query": "q"})

        assert degraded["degraded_sources"] == ["opc"]


# ── SSE 入口契約（旗標 >= pre） ──────────────────────────────


def _iter_sse_events(resp) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    current = ""
    for line in resp.iter_lines():
        if not line:
            continue
        if line.startswith("event:"):
            current = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            try:
                payload = json.loads(line.split("data:", 1)[1].strip())
            except json.JSONDecodeError:
                continue
            events.append((current, payload))
    return events


def _patch_llm_trio():
    def fake_stream(prompt, system=None, model=None, **kwargs):
        yield "ok"

    def fake_eval(prompt, system=None, model=None, **kwargs):
        return json.dumps({"score": 9.0, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)

    return (
        patch("backend.main.call_llm_stream", side_effect=fake_stream),
        patch("backend.core.nodes.call_llm", side_effect=fake_eval),
        patch("backend.core.evaluation.call_llm", side_effect=fake_eval),
    )


class TestSsePreEnhancements:
    def _run_stream(self, query: str):
        from fastapi.testclient import TestClient

        from backend.main import app

        store = MagicMock()
        store.search_similar.return_value = []
        p1, p2, p3 = _patch_llm_trio()
        with (
            p1,
            p2,
            p3,
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,
            client.stream(
                "POST",
                "/chat/stream",
                json={"query": query, "execution_strategy": "simple"},
            ) as resp,
        ):
            assert resp.status_code == 200
            return _iter_sse_events(resp)

    @pytest.mark.parametrize("flag", ["pre", "reflect", "full"])
    def test_flag_on_runs_opc_and_linkin(self, monkeypatch, flag):
        monkeypatch.setenv("EVOL_UNIFIED_PIPELINE", flag)
        calls: list[str] = []

        async def opc(_state):
            calls.append("opc")
            return {"opc_context": {"opc_status": "not_required"}}

        def linkin(_state):
            calls.append("linkin")
            return {"linkin_context": {}}

        def recall(_state):
            calls.append("recall")
            return {}

        with (
            patch(OPC_MOD, side_effect=opc),
            patch(LINKIN_MOD, side_effect=linkin),
            patch(RECALL_MOD, side_effect=recall),
        ):
            events = self._run_stream("今天天氣如何")

        assert set(calls) == {"opc", "linkin", "recall"}
        phases = [p["phase"] for e, p in events if e == "phase" and "phase" in p]
        for phase in ("enhance_opc_context", "enhance_linkin_context", "enhance_recall_context"):
            assert phase in phases

    def test_flag_off_keeps_recall_only(self, monkeypatch):
        monkeypatch.setenv("EVOL_UNIFIED_PIPELINE", "off")
        calls: list[str] = []

        async def opc(_state):
            calls.append("opc")
            return {}

        def recall(_state):
            calls.append("recall")
            return {}

        with patch(OPC_MOD, side_effect=opc), patch(RECALL_MOD, side_effect=recall):
            events = self._run_stream("今天天氣如何")

        assert calls == ["recall"]
        phases = [p["phase"] for e, p in events if e == "phase" and "phase" in p]
        assert "enhance_opc_context" not in phases
        done = next(p for e, p in events if e == "done")
        assert "context_degraded" not in done

    def test_degraded_surfaces_on_path_resolved_and_done(self, monkeypatch):
        monkeypatch.setenv("EVOL_UNIFIED_PIPELINE", "pre")
        monkeypatch.setenv("EVOL_PRE_ENHANCE_TIMEOUT_MS", "40")

        async def slow_opc(_state):
            await asyncio.sleep(5)
            return {}

        def fast(_state):
            return {}

        with patch(OPC_MOD, side_effect=slow_opc), patch(LINKIN_MOD, side_effect=fast), patch(
            RECALL_MOD, side_effect=fast
        ):
            events = self._run_stream("產線馬達溫度感測異常")

        done = next(p for e, p in events if e == "done")
        assert done["context_degraded"] is True
        assert done["degraded_sources"] == ["opc"]

        path_resolved = [p for e, p in events if e == "path_resolved"]
        assert any(p.get("context_degraded") and p.get("degraded_sources") == ["opc"] for p in path_resolved)
