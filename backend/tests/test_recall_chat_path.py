"""主聊天路徑整合召回測試（ContextAssembler fail-open 注入）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core import nodes
from backend.core.graph import build_graph
from backend.integrations import api as integ_api
from backend.integrations.openviking import OpenVikingClient
from backend.integrations.recall_bridge import (
    assemble_recall_context,
    enhance_with_recall_context,
    prefix_query_with_recall,
)
from backend.tests.test_integrations import _cfg, _transport_ok


def _evaluation(score: float) -> str:
    return json.dumps({"score": score, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)


def _fake_registry(viking_transport):
    return {
        "memos": MagicMock(http=MagicMock(enabled=False)),
        "openviking": OpenVikingClient(config=_cfg("openviking"), transport=viking_transport),
        "weknora": MagicMock(http=MagicMock(enabled=False)),
        "yao": MagicMock(http=MagicMock(enabled=False)),
        "ouroboros": MagicMock(http=MagicMock(enabled=False)),
        "openpencil": MagicMock(http=MagicMock(enabled=False)),
    }


@pytest.fixture(autouse=True)
def _reset_integration_registry():
    integ_api.reset_registry()
    yield
    integ_api.reset_registry()


def test_graph_includes_recall_node():
    names = set(build_graph().get_graph().nodes)
    assert "enhance_with_recall_context" in names


def test_enhance_injects_openviking_fragment_into_generate_prompt(monkeypatch):
    def _viking_transport(method, url, headers, body, timeout):
        if url.endswith("/api/v1/search/find"):
            return 200, json.dumps(
                {"results": [{"uri": "viking://ctx/a", "score": 0.9}]}
            ).encode()
        return 200, json.dumps({"content": "OpenViking 上下文摘要"}).encode()

    monkeypatch.setattr(integ_api, "get_registry", lambda: _fake_registry(_viking_transport))

    update = enhance_with_recall_context(
        {"query": "今天任務是什麼", "history": [{"role": "user", "content": "你好"}]}
    )
    assert "openviking" in update["recall_context"]["injection"]
    assert "recall_assembled" in update["recall_context"]["reason_codes"]

    captured: dict = {}

    def fake_llm(prompt, system=None, model=None, **kwargs):
        captured["prompt"] = prompt
        return "回答"

    monkeypatch.setattr(nodes, "call_llm", fake_llm)
    monkeypatch.setattr(nodes, "resolve_stage_model", lambda *a, **k: "m")
    monkeypatch.setattr(nodes, "log_node", lambda *a, **k: None)

    state = {"query": "今天任務是什麼", "history": [], "retrieved_memories": [], **update}
    nodes.generate_initial_answer(state)
    assert "OpenViking 上下文摘要" in captured["prompt"]
    assert "【整合召回】" in captured["prompt"]


def test_recall_disabled_does_not_break_graph_invoke(monkeypatch):
    monkeypatch.setattr(integ_api, "get_registry", lambda: _fake_registry(_transport_ok({})))
    fake_responses = ["足夠長度的初始回答內容。", _evaluation(9)]

    def fake_llm(prompt, system=None, model=None, **kwargs):
        return fake_responses.pop(0)

    with (
        patch("backend.core.nodes.call_llm", side_effect=fake_llm),
        patch("backend.core.evaluation.call_llm", side_effect=fake_llm),
        patch("backend.core.nodes._memory_store") as mock_store,
    ):
        mock_store.search_similar.return_value = []
        result = build_graph().invoke({"query": "簡單問題", "execution_strategy": "simple"})

    assert result["final_answer"]
    recall = result.get("recall_context") or {}
    assert recall.get("injection", "") == "" or "recall" in " ".join(recall.get("reason_codes", []))


def test_assembler_exception_fail_open(monkeypatch):
    monkeypatch.setattr(
        "backend.integrations.recall_bridge.assemble_recall_context",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    assert enhance_with_recall_context({"query": "q", "history": []}) == {}


def test_company_path_prefixes_recall_injection():
    state = {
        "query": "設計登入頁",
        "recall_context": {"injection": "[openviking:L0] 相關背景"},
    }
    prefixed = prefix_query_with_recall(state["query"], state)
    assert "【整合召回上下文】" in prefixed
    assert "openviking" in prefixed
    assert "設計登入頁" in prefixed


def test_build_generate_prompt_uses_truncated_history_from_recall(monkeypatch):
    monkeypatch.setattr(integ_api, "get_registry", lambda: _fake_registry(_transport_ok({})))
    long_history = [{"role": "user", "content": f"輪次{i}"} for i in range(10)]
    recall_update = enhance_with_recall_context({"query": "q", "history": long_history})
    state = {"query": "q", "history": recall_update["history"], **recall_update}
    prompt, _ = nodes.build_generate_prompt(state)
    assert "輪次9" in prompt
    assert "轮次0" not in prompt


def test_assemble_recall_context_via_bridge_matches_api_contract(monkeypatch):
    def _viking_transport(method, url, headers, body, timeout):
        if url.endswith("/api/v1/search/find"):
            return 200, json.dumps({"results": [{"uri": "viking://x", "score": 0.8}]}).encode()
        return 200, json.dumps({"content": "片段"}).encode()

    monkeypatch.setattr(integ_api, "get_registry", lambda: _fake_registry(_viking_transport))
    out = assemble_recall_context("查詢", [{"role": "user", "content": "hi"}])
    assert any("openviking" in f["source"] for f in out.fragments)
    assert out.render_injection()
