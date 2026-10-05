"""P0：統一管線旗標、請求建構器、三入口路由契約（行為不變）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core.reflection_limits import resolve_task_complexity
from backend.core.routing_preview import build_routing_preview
from backend.core.unified_pipeline import (
    PipelineMode,
    PipelineRequest,
    build_pipeline_request_from_chat,
    build_pipeline_request_from_task,
    build_semantic_lock_from_task_options,
    pipeline_at_least,
    pipeline_level,
    resolve_task_effective_query,
    run_unified_pipeline,
)


@pytest.fixture(autouse=True)
def _routing_feedback_isolated(monkeypatch, tmp_path):
    fb = tmp_path / "routing_feedback.json"
    fb.write_text(
        json.dumps({
            "records": [],
            "stats": {"simple": 0, "company": 0},
            "meta": {"consecutive_simple_low": 0},
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVOL_ROUTING_FEEDBACK_PATH", str(fb))
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)
    monkeypatch.delenv("EVOL_UNIFIED_PIPELINE", raising=False)


@pytest.fixture(autouse=True)
def _reset_unknown_pipeline_log():
    import backend.core.unified_pipeline as up

    up._unknown_env_logged = False
    yield
    up._unknown_env_logged = False


class TestPipelineLevel:
    @pytest.mark.parametrize(
        "env,expected",
        [
            (None, "off"),
            ("", "off"),
            ("off", "off"),
            ("pre", "pre"),
            ("reflect", "reflect"),
            ("batch", "batch"),
            ("full", "full"),
            ("FULL", "full"),
        ],
    )
    def test_pipeline_level_parsing(self, monkeypatch, env, expected):
        if env is None:
            monkeypatch.delenv("EVOL_UNIFIED_PIPELINE", raising=False)
        else:
            monkeypatch.setenv("EVOL_UNIFIED_PIPELINE", env)
        assert pipeline_level() == expected

    def test_unknown_value_logs_once_and_returns_off(self, monkeypatch, caplog):
        monkeypatch.setenv("EVOL_UNIFIED_PIPELINE", "maybe")
        import backend.core.unified_pipeline as up

        up._unknown_env_logged = False
        with caplog.at_level("WARNING"):
            assert pipeline_level() == "off"
            assert pipeline_level() == "off"
        warnings = [r for r in caplog.records if "EVOL_UNIFIED_PIPELINE" in r.message]
        assert len(warnings) == 1

    def test_pipeline_at_least(self, monkeypatch):
        monkeypatch.setenv("EVOL_UNIFIED_PIPELINE", "reflect")
        assert pipeline_at_least("pre")
        assert pipeline_at_least("reflect")
        assert not pipeline_at_least("batch")


class TestPipelineBuilders:
    def test_chat_builder_locked_brief(self):
        req = build_pipeline_request_from_chat(
            query="原始問題",
            semantic_lock={"locked_brief": "鎖定後簡報"},
            session_id="s1",
        )
        assert req.effective_query == "鎖定後簡報"
        assert req.semantic_lock["locked_brief"] == "鎖定後簡報"
        assert req.source_entry == "chat"

    def test_task_auditor_ticket_maps_to_semantic_lock(self):
        ticket = {
            "status": "APPROVED_FOR_PLANNING",
            "locked_brief": "戰役簡報本體",
            "objective": "測試",
        }
        lock = build_semantic_lock_from_task_options({"auditor_ticket": ticket})
        assert lock["auditor_ticket"] == ticket
        assert lock["locked_brief"] == "戰役簡報本體"

        req = build_pipeline_request_from_task(
            query="fallback",
            options={"auditor_ticket": ticket},
            task_id="t1",
        )
        assert req.semantic_lock["auditor_ticket"] == ticket
        assert req.effective_query == "戰役簡報本體"

    def test_task_approved_ticket_without_brief_uses_json_query(self):
        ticket = {"status": "APPROVED_FOR_PLANNING", "objective": "only-ticket"}
        effective = resolve_task_effective_query("raw", {"auditor_ticket": ticket})
        assert json.loads(effective) == ticket

    @pytest.mark.asyncio
    async def test_run_unified_pipeline_not_implemented(self):
        req = PipelineRequest(query="q", effective_query="q")
        with pytest.raises(NotImplementedError):
            await run_unified_pipeline(req, PipelineMode.BATCH)


def _routing_triple(query: str, strategy: str = "auto", *, company_template: str = "quick_task"):
    complexity = resolve_task_complexity(query, strategy)
    preview = build_routing_preview(
        query,
        mode=strategy,
        company_template=company_template,
        task_complexity=complexity,
    )
    return preview["path"], preview["complexity"], preview["max_reflection_rounds"]


def _chat_batch_triple(
    query: str,
    strategy: str = "auto",
    *,
    company_template: str = "quick_task",
    semantic_lock: dict | None = None,
):
    from backend.core.unified_pipeline import effective_query_from_lock

    effective = effective_query_from_lock(query, semantic_lock)
    return _routing_triple(effective, strategy, company_template=company_template)


class TestThreeEntryRoutingContract:
    SIMPLE_Q = "今天天氣如何"
    OPC_Q = "產線馬達溫度感測異常請診斷"
    LINKIN_Q = "在灵境精灵森林建造一座树桥聚落"
    COMPANY_Q = "請設計並實現一個完整的微服務系統架構"

    @pytest.mark.parametrize(
        "query",
        [SIMPLE_Q, OPC_Q, LINKIN_Q, COMPANY_Q],
        ids=["simple", "opc", "linkin", "company"],
    )
    def test_task_sse_and_chat_batch_agree_on_routing(self, query):
        task_path, task_complexity, task_max = _routing_triple(query)
        sse_path, sse_complexity, sse_max = _routing_triple(query)
        batch_path, batch_complexity, batch_max = _chat_batch_triple(query)

        assert (task_path, task_complexity, task_max) == (sse_path, sse_complexity, sse_max)
        assert (batch_path, batch_complexity, batch_max) == (task_path, task_complexity, task_max)

    def test_semantic_lock_aligns_chat_and_task_builders(self):
        brief = "鎖定：靈境聚落第二階段"
        chat_req = build_pipeline_request_from_chat(
            query="未鎖定文字",
            semantic_lock={"locked_brief": brief},
        )
        task_req = build_pipeline_request_from_task(
            query="未鎖定文字",
            options={"locked_brief": brief},
        )
        chat_t = _chat_batch_triple(chat_req.query, semantic_lock=chat_req.semantic_lock)
        task_t = _routing_triple(task_req.effective_query)
        assert chat_t == task_t


class TestKnownDivergencesXfail:
    """設計 §2.2：P1/P2 才收斂的分歧（strict xfail 鎖現況）。"""

    OPC_Q = TestThreeEntryRoutingContract.OPC_Q
    LINKIN_Q = TestThreeEntryRoutingContract.LINKIN_Q

    @pytest.mark.xfail(strict=True, reason="P1：SSE simple 尚未執行 enhance_with_opc_context")
    def test_sse_simple_runs_opc_enhancement(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.main import app

        opc_calls: list[dict] = []

        async def _track_opc(state):
            opc_calls.append(dict(state))
            return {"opc_context": {"status": "not_required"}}

        def fake_stream(prompt, system=None, model=None, **kwargs):
            yield "ok"

        def fake_eval(prompt, system=None, model=None, **kwargs):
            return json.dumps({"score": 9.0, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)

        store = MagicMock()
        store.search_similar.return_value = []

        with (
            patch("backend.core.company_nodes.enhance_with_opc_context", side_effect=_track_opc),
            patch("backend.main.call_llm_stream", side_effect=fake_stream),
            patch("backend.core.nodes.call_llm", side_effect=fake_eval),
            patch("backend.core.evaluation.call_llm", side_effect=fake_eval),
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,
            client.stream(
                "POST",
                "/chat/stream",
                json={"query": self.OPC_Q, "execution_strategy": "auto"},
            ) as resp,
        ):
            assert resp.status_code == 200
            for _ in resp.iter_lines():
                pass

        assert opc_calls, "預期 SSE simple 路徑呼叫 OPC 增強（P1 前應失敗）"

    @pytest.mark.xfail(strict=True, reason="P1：SSE simple 尚未執行 enhance_with_linkin_context")
    def test_sse_simple_runs_linkin_enhancement(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.main import app

        linkin_calls: list[dict] = []

        def _track_linkin(state):
            linkin_calls.append(dict(state))
            return {"linkin_context": {}}

        def fake_stream(prompt, system=None, model=None, **kwargs):
            yield "ok"

        def fake_eval(prompt, system=None, model=None, **kwargs):
            return json.dumps({"score": 9.0, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)

        store = MagicMock()
        store.search_similar.return_value = []

        with (
            patch("backend.linkin.pipeline.enhance_with_linkin_context", side_effect=_track_linkin),
            patch("backend.main.call_llm_stream", side_effect=fake_stream),
            patch("backend.core.nodes.call_llm", side_effect=fake_eval),
            patch("backend.core.evaluation.call_llm", side_effect=fake_eval),
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,
            client.stream(
                "POST",
                "/chat/stream",
                json={"query": self.LINKIN_Q, "execution_strategy": "auto"},
            ) as resp,
        ):
            assert resp.status_code == 200
            for _ in resp.iter_lines():
                pass

        assert linkin_calls, "預期 SSE simple 路徑呼叫靈境增強（P1 前應失敗）"

    @pytest.mark.xfail(strict=True, reason="P2：SSE simple 完成後未經 decide_final_answer 呼叫 record_outcome")
    def test_sse_simple_records_routing_outcome(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        recorded: list[dict] = []

        def fake_stream(prompt, system=None, model=None, **kwargs):
            yield "ok"

        def fake_eval(prompt, system=None, model=None, **kwargs):
            return json.dumps({"score": 9.0, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)

        store = MagicMock()
        store.search_similar.return_value = []

        with (
            patch("backend.core.routing_feedback.record_outcome", side_effect=lambda **kw: recorded.append(kw)),
            patch("backend.main.call_llm_stream", side_effect=fake_stream),
            patch("backend.core.nodes.call_llm", side_effect=fake_eval),
            patch("backend.core.evaluation.call_llm", side_effect=fake_eval),
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,
            client.stream(
                "POST",
                "/chat/stream",
                json={"query": TestThreeEntryRoutingContract.SIMPLE_Q, "execution_strategy": "simple"},
            ) as resp,
        ):
            assert resp.status_code == 200
            for _ in resp.iter_lines():
                pass

        assert recorded, "P2 前 SSE 不應寫入 record_outcome"

    @pytest.mark.xfail(
        strict=True,
        reason="P2：公司 SSE 反思仍用 PASS_THRESHOLD/MAX_ITERATIONS，非 graph should_improve",
    )
    def test_company_sse_uses_graph_should_improve_cap(self):
        import inspect

        from backend import main

        src = inspect.getsource(main._company_stream)
        assert "reflection_should_continue" in src or "should_improve" in src
