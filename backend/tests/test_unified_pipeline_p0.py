"""P0：統一管線旗標、請求建構器、三入口路由契約（行為不變）。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.core.company_nodes import route_by_complexity
from backend.core.execution_path import chat_stream_uses_company_sse, resolve_execution_path
from backend.core.reflection_limits import reflection_max_iterations, resolve_task_complexity
from backend.core.routing_preview import build_routing_preview
from backend.core.unified_pipeline import (
    PipelineMode,
    PipelineRequest,
    build_pipeline_request_from_chat,
    build_pipeline_request_from_task,
    build_semantic_lock_from_task_options,
    effective_query_from_lock,
    pipeline_at_least,
    pipeline_level,
    resolve_task_effective_query,
    run_unified_pipeline,
)
from backend.services.task_manager import TaskManager


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


@pytest.fixture
def task_manager_no_redis():
    mgr = TaskManager()
    with patch.object(mgr, "_persist", MagicMock()), patch.object(mgr, "_get_redis", return_value=None):
        yield mgr


def _graph_target_to_exec_path(target: str) -> str:
    return {
        "run_company": "company",
        "run_minecraft_ops": "minecraft_ops",
        "generate_initial_answer": "simple",
    }[target]


def routing_snapshot_chat_sync(
    query: str,
    strategy: str = "auto",
    *,
    semantic_lock: dict[str, Any] | None = None,
    company_template: str = "quick_task",
) -> dict[str, Any]:
    """``POST /chat``：圖上 ``route_by_complexity`` + 與 preview 同源的 path／輪次解析。"""
    effective = effective_query_from_lock(query, semantic_lock)
    state: dict[str, Any] = {
        "query": effective,
        "execution_strategy": strategy,
    }
    target = route_by_complexity(state)
    resolve_path = resolve_execution_path(
        effective,
        strategy,
        task_complexity=state.get("task_complexity"),
    )
    complexity = resolve_task_complexity(effective, strategy)
    max_rounds = reflection_max_iterations(
        {
            "query": effective,
            "execution_strategy": strategy,
            "task_complexity": complexity,
            "resolved_execution_path": resolve_path,
        },
        routing_preview=True,
    )
    _ = company_template
    return {
        "target": target,
        "exec_path": _graph_target_to_exec_path(target),
        "resolve_path": resolve_path,
        "complexity": complexity,
        "max_reflection_rounds": max_rounds,
    }


def routing_snapshot_task(
    mgr: TaskManager,
    query: str,
    strategy: str = "auto",
    *,
    template: str = "quick_task",
    options: dict[str, Any] | None = None,
) -> tuple[str, str, int]:
    """``TaskManager._run_unified_task`` 開頭相同的三元組。"""
    record = mgr.create_task(query, strategy, template, options=options or {})
    record.task_complexity = resolve_task_complexity(record.query, record.strategy)
    preview = build_routing_preview(
        record.query,
        mode=record.strategy,
        company_template=record.template,
        task_complexity=record.task_complexity,
    )
    return (
        str(preview["path"]),
        str(preview["complexity"]),
        int(preview["max_reflection_rounds"]),
    )


def routing_snapshot_sse(
    query: str,
    strategy: str = "auto",
    *,
    semantic_lock: dict[str, Any] | None = None,
    company_template: str = "quick_task",
) -> dict[str, Any]:
    """``chat_stream`` 分支 + 各分支內 ``build_routing_preview`` 呼叫方式。"""
    effective = effective_query_from_lock(query, semantic_lock)

    if chat_stream_uses_company_sse(query, strategy):
        branch = "company"
        preview = build_routing_preview(
            effective,
            mode=strategy,
            company_template=company_template,
        )
    elif resolve_execution_path(query, strategy) == "minecraft_ops":
        branch = "minecraft_ops"
        preview = build_routing_preview(
            effective,
            mode=strategy,
            company_template=company_template,
        )
    else:
        branch = "simple"
        preview = build_routing_preview(
            effective,
            mode=strategy,
            company_template=company_template,
        )

    return {
        "branch": branch,
        "path": str(preview["path"]),
        "complexity": str(preview["complexity"]),
        "max_reflection_rounds": int(preview["max_reflection_rounds"]),
    }


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
        assert "locked_brief" not in lock

        req = build_pipeline_request_from_task(
            query="fallback",
            options={"auditor_ticket": ticket},
            task_id="t1",
        )
        assert req.semantic_lock["auditor_ticket"] == ticket
        assert req.effective_query == json.dumps(ticket, ensure_ascii=False)

    def test_task_approved_ticket_without_brief_uses_json_query(self):
        ticket = {"status": "APPROVED_FOR_PLANNING", "objective": "only-ticket"}
        effective = resolve_task_effective_query("raw", {"auditor_ticket": ticket})
        assert json.loads(effective) == ticket

    @pytest.mark.asyncio
    async def test_run_unified_pipeline_not_implemented(self):
        req = PipelineRequest(query="q", effective_query="q")
        with pytest.raises(NotImplementedError):
            await run_unified_pipeline(req, PipelineMode.BATCH)


class TestTaskCreateQueryAlignment:
    @pytest.mark.parametrize(
        "raw,options",
        [
            ("raw-q", {}),
            ("  padded raw  ", {}),
            ("raw-q", {"locked_brief": "  brief-only  "}),
            ("raw-q", {"semantic_brief": "semantic-wins"}),
            (
                "raw-q",
                {
                    "locked_brief": "brief-first",
                    "auditor_ticket": {"status": "APPROVED_FOR_PLANNING", "objective": "x"},
                },
            ),
            (
                "raw-q",
                {"auditor_ticket": {"status": "APPROVED_FOR_PLANNING", "objective": "only-ticket"}},
            ),
            (
                "raw-q",
                {
                    "auditor_ticket": {
                        "status": "APPROVED_FOR_PLANNING",
                        "locked_brief": "in-ticket-not-used-for-query",
                    },
                },
            ),
            (
                "raw-q",
                {
                    "semantic_brief": "combo-brief",
                    "auditor_ticket": {"status": "APPROVED_FOR_PLANNING", "objective": "y"},
                },
            ),
        ],
        ids=[
            "plain",
            "raw_query_whitespace_preserved",
            "locked_brief",
            "semantic_brief",
            "brief_before_ticket",
            "approved_ticket_json",
            "ticket_locked_brief_still_json",
            "semantic_brief_and_ticket",
        ],
    )
    def test_create_task_query_matches_resolve_helper(
        self, task_manager_no_redis, raw, options
    ):
        expected = resolve_task_effective_query(raw, options)
        record = task_manager_no_redis.create_task(
            raw, "auto", "quick_task", options=dict(options)
        )
        assert record.query == expected
        req = build_pipeline_request_from_task(query=raw, options=dict(options))
        assert req.effective_query == expected
        lock_brief = req.semantic_lock.get("locked_brief")
        if lock_brief is not None:
            assert lock_brief == req.effective_query


class TestThreeEntryRoutingContract:
    SIMPLE_Q = "今天天氣如何"
    OPC_Q = "產線馬達溫度感測異常請診斷"
    LINKIN_Q = "在灵境精灵森林建造一座树桥聚落"
    COMPANY_Q = "請設計並實現一個完整的微服務系統架構"

    @pytest.mark.parametrize(
        "query",
        [SIMPLE_Q, LINKIN_Q, COMPANY_Q],
        ids=["simple", "linkin", "company"],
    )
    def test_task_sse_and_chat_resolve_agree(self, task_manager_no_redis, query):
        task = routing_snapshot_task(task_manager_no_redis, query)
        sse = routing_snapshot_sse(query)
        chat = routing_snapshot_chat_sync(query)

        assert task == (sse["path"], sse["complexity"], sse["max_reflection_rounds"])
        assert chat["resolve_path"] == task[0]
        assert chat["complexity"] == task[1]
        assert chat["max_reflection_rounds"] == task[2]
        assert chat["exec_path"] == task[0]

    def test_opc_q1_task_label_vs_chat_graph_execution(self, task_manager_no_redis):
        task = routing_snapshot_task(task_manager_no_redis, self.OPC_Q)
        sse = routing_snapshot_sse(self.OPC_Q)
        chat = routing_snapshot_chat_sync(self.OPC_Q)

        assert task[0] == "opc"
        assert sse["path"] == "opc"
        assert chat["resolve_path"] == "opc"
        assert chat["target"] == "generate_initial_answer"
        assert chat["exec_path"] == "simple"
        assert task[1:] == (sse["complexity"], sse["max_reflection_rounds"])
        assert chat["complexity"] == task[1]
        assert chat["max_reflection_rounds"] == task[2]

    def test_semantic_lock_aligns_chat_sse_and_task(self, task_manager_no_redis):
        brief = "鎖定：靈境聚落第二階段"
        chat_req = build_pipeline_request_from_chat(
            query="未鎖定文字",
            semantic_lock={"locked_brief": brief},
        )
        task = routing_snapshot_task(
            task_manager_no_redis,
            "未鎖定文字",
            options={"locked_brief": brief},
        )
        sse = routing_snapshot_sse(
            chat_req.query,
            semantic_lock=chat_req.semantic_lock,
        )
        chat = routing_snapshot_chat_sync(
            chat_req.query,
            semantic_lock=chat_req.semantic_lock,
        )
        assert task == (sse["path"], sse["complexity"], sse["max_reflection_rounds"])
        assert chat["resolve_path"] == task[0]


def _collect_sse_phases(resp) -> list[str]:
    phases: list[str] = []
    for line in resp.iter_lines():
        if not line or not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line.split("data:", 1)[1].strip())
        except json.JSONDecodeError:
            continue
        phase = payload.get("phase")
        if phase:
            phases.append(str(phase))
    return phases


class TestEnhancementProbePositiveControls:
    @staticmethod
    def _simple_record(task_manager_no_redis: TaskManager, query: str) -> Any:
        record = task_manager_no_redis.create_task(query, "auto", "quick_task")
        record.resolved_path = "simple"
        record.task_complexity = "simple"
        return record

    @pytest.mark.asyncio
    async def test_simple_task_path_calls_opc_enhancement(self, task_manager_no_redis):
        import backend.services.task_manager as tm

        opc_calls: list[str] = []
        cancel_checks = iter([False, True])

        async def track_opc(state):
            opc_calls.append(str(state.get("query")))
            return {"opc_context": {"status": "not_required"}}

        record = self._simple_record(task_manager_no_redis, "今天天氣如何")
        store = MagicMock()
        store.search_similar.return_value = []

        mock_tracer = MagicMock()
        with (
            patch.object(tm, "enhance_with_opc_context", side_effect=track_opc),
            patch("backend.core.nodes.retrieve_memories", return_value={}),
            patch("backend.core.nodes._memory_store", store),
            patch.object(task_manager_no_redis, "_check_cancelled", side_effect=lambda _r: next(cancel_checks, True)),
            patch.object(task_manager_no_redis, "_finish", MagicMock()),
            patch("backend.services.task_manager.TraceLogger", MagicMock(return_value=mock_tracer)),
        ):
            await task_manager_no_redis._run_simple_task(record)

        assert opc_calls == [record.query]

    @pytest.mark.asyncio
    async def test_simple_task_path_calls_linkin_enhancement(self, task_manager_no_redis):
        import backend.services.task_manager as tm

        linkin_calls: list[str] = []
        cancel_checks = iter([False, False, True])

        def track_linkin(state):
            linkin_calls.append(str(state.get("query")))
            return {"linkin_context": {}}

        async def passthrough_opc(_state):
            return {"opc_context": {"status": "not_required"}}

        record = self._simple_record(task_manager_no_redis, TestThreeEntryRoutingContract.LINKIN_Q)
        store = MagicMock()
        store.search_similar.return_value = []

        mock_tracer = MagicMock()
        with (
            patch.object(tm, "enhance_with_opc_context", side_effect=passthrough_opc),
            patch.object(tm, "enhance_with_linkin_context", side_effect=track_linkin),
            patch("backend.core.nodes.retrieve_memories", return_value={}),
            patch("backend.core.nodes._memory_store", store),
            patch.object(task_manager_no_redis, "_check_cancelled", side_effect=lambda _r: next(cancel_checks, True)),
            patch.object(task_manager_no_redis, "_finish", MagicMock()),
            patch("backend.services.task_manager.TraceLogger", MagicMock(return_value=mock_tracer)),
        ):
            await task_manager_no_redis._run_simple_task(record)

        assert linkin_calls == [record.query]

    def test_record_outcome_patch_intercepts_decide_final_answer(self):
        recorded: list[dict] = []

        def capture(**kwargs):
            recorded.append(kwargs)

        from backend.core import nodes

        state = {
            "query": "q",
            "current_answer": "answer",
            "final_answer": "answer",
            "score": 8.0,
            "iteration": 0,
            "resolved_execution_path": "simple",
            "execution_strategy": "auto",
        }
        with patch("backend.core.routing_feedback.record_outcome", side_effect=capture):
            nodes.decide_final_answer(state)
        assert recorded


class TestKnownDivergencesXfail:
    """設計 §2.2：P1/P2 才收斂的分歧（strict xfail + raises=AssertionError）。"""

    OPC_Q = TestThreeEntryRoutingContract.OPC_Q
    LINKIN_Q = TestThreeEntryRoutingContract.LINKIN_Q
    SIMPLE_Q = TestThreeEntryRoutingContract.SIMPLE_Q

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="P1：SSE simple 尚未執行 enhance_with_opc_context（應 patch backend.main 匯入點）",
    )
    def test_sse_simple_runs_opc_enhancement(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        opc_calls: list[str] = []

        async def track_opc(_state):
            opc_calls.append("opc")
            return {"opc_context": {"status": "not_required"}}

        def fake_stream(prompt, system=None, model=None, **kwargs):
            yield "ok"

        def fake_eval(prompt, system=None, model=None, **kwargs):
            return json.dumps({"score": 9.0, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)

        store = MagicMock()
        store.search_similar.return_value = []

        import backend.main as main_mod

        with (
            patch.object(main_mod, "enhance_with_opc_context", new=track_opc, create=True),
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

        assert opc_calls, "P1 後應在 SSE simple 路徑呼叫 OPC 增強"

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="P1：SSE simple 尚未執行 enhance_with_linkin_context（應 patch backend.main 匯入點）",
    )
    def test_sse_simple_runs_linkin_enhancement(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        linkin_calls: list[str] = []

        def track_linkin(_state):
            linkin_calls.append("linkin")
            return {"linkin_context": {}}

        def fake_stream(prompt, system=None, model=None, **kwargs):
            yield "ok"

        def fake_eval(prompt, system=None, model=None, **kwargs):
            return json.dumps({"score": 9.0, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)

        store = MagicMock()
        store.search_similar.return_value = []

        import backend.main as main_mod

        with (
            patch.object(main_mod, "enhance_with_linkin_context", side_effect=track_linkin, create=True),
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

        assert linkin_calls, "P1 後應在 SSE simple 路徑呼叫靈境增強"

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="P2：SSE simple 完成後未經 decide_final_answer 呼叫 record_outcome",
    )
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
                json={"query": self.SIMPLE_Q, "execution_strategy": "simple"},
            ) as resp,
        ):
            assert resp.status_code == 200
            for _ in resp.iter_lines():
                pass

        assert recorded, "P2 後 SSE 應經 finalize/decide 寫入 record_outcome"

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="P2：公司 SSE 反思未尊重 should_improve（低分仍進 reflect）",
    )
    def test_company_sse_respects_should_improve(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.company.orchestrator import CompanyOrchestrator
        from backend.main import app

        monkeypatch.setenv("EVOL_POST_COMPANY_REFLECT", "full")
        monkeypatch.setattr(
            "backend.core.graph.should_improve",
            lambda _state: "finalize",
        )

        async def _fake_execute(self, query):
            return {"final_output": "公司產出", "success": True, "stats": {}}

        def fake_eval(state):
            return {**state, "score": 5.0, "multi_dim_evaluation": {}}

        def fake_reflect(state):
            return {**state, "iteration": int(state.get("iteration") or 0) + 1}

        monkeypatch.setattr(CompanyOrchestrator, "execute", _fake_execute)
        monkeypatch.setattr("backend.main.nodes.evaluate_answer", fake_eval)
        monkeypatch.setattr("backend.main.nodes.reflect", fake_reflect)
        monkeypatch.setattr("backend.main.nodes.improve_answer", lambda s: s)
        monkeypatch.setattr("backend.main.nodes.enforce_output_length", lambda s: s)
        monkeypatch.setattr("backend.main.nodes.save_memory", lambda s: s)

        phases: list[str] = []
        with TestClient(app) as client, client.stream(
            "POST",
            "/chat/stream",
            json={
                "query": TestThreeEntryRoutingContract.COMPANY_Q,
                "execution_strategy": "company",
            },
        ) as resp:
            assert resp.status_code == 200
            phases = _collect_sse_phases(resp)

        assert "reflect" not in phases, "should_improve=finalize 時不應進入 reflect 階段"
