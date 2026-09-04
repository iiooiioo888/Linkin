"""靈境統一管線注入：非靈境查詢不得改路由；命中世界觀才注入 RAG。"""

from __future__ import annotations

import pytest

from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.pipeline import (
    enhance_with_linkin_context,
    is_linkin_complex_task,
    needs_linkin_context,
    resolve_linkin_company_template,
)


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    reset_store()
    reset_constitution_cache()
    yield tmp_path
    reset_store()
    reset_constitution_cache()


def test_non_linkin_query_skips_context():
    assert needs_linkin_context("測試問題") is False
    assert is_linkin_complex_task("測試問題") is False
    assert enhance_with_linkin_context({"query": "測試問題"}) == {"linkin_context": {}}


def test_world_query_is_simple_dialogue():
    query = "织庭都还欢迎旅人吗？"
    assert needs_linkin_context(query) is True
    assert is_linkin_complex_task(query) is False


def test_build_query_is_complex():
    query = "在精灵森林建造一座月光庭园主城"
    assert needs_linkin_context(query) is True
    assert is_linkin_complex_task(query) is True


def test_enhance_injects_constitution(linkin_env):
    result = enhance_with_linkin_context({"query": "灵境的三大阵营是什么？"})
    ctx = result["linkin_context"]
    assert ctx["active"] is True
    assert "靈境世界觀憲法" in ctx["summary"] or "灵境" in ctx["summary"]
    assert "织庭" in ctx["summary"] or "織庭" in ctx["summary"]
    assert ctx["system_overlay"]


def test_route_linkin_complex_to_company():
    from backend.core.company_nodes import route_by_complexity

    state = {"query": "在灵境精灵森林建造一座树桥聚落", "execution_strategy": "auto"}
    assert route_by_complexity(state) == "run_company"


def test_route_generic_query_unchanged():
    from backend.core.company_nodes import route_by_complexity

    state = {"query": "今天天氣如何", "execution_strategy": "auto"}
    assert route_by_complexity(state) == "generate_initial_answer"


def test_story_studio_only_for_default_template():
    state = {
        "query": "在灵境建造一座白石圣殿",
        "company_template": "quick_task",
        "linkin_context": {"active": True, "complex": True},
    }
    assert resolve_linkin_company_template(state) == "story_studio"
    state["company_template"] = "full_company"
    assert resolve_linkin_company_template(state) is None


def test_graph_includes_linkin_node():
    from backend.core.graph import build_graph

    compiled = build_graph()
    names = set(compiled.get_graph().nodes)
    assert "enhance_with_linkin_context" in names
    assert "enhance_with_opc_context" in names


def test_generate_injects_linkin_overlay(monkeypatch):
    from backend.core import nodes

    captured: dict = {}

    def fake_llm(prompt, system=None, model=None, **kwargs):
        captured["prompt"] = prompt
        captured["system"] = system
        return "ok"

    monkeypatch.setattr(nodes, "call_llm", fake_llm)
    monkeypatch.setattr(nodes, "resolve_stage_model", lambda *a, **k: "m")
    monkeypatch.setattr(nodes, "log_node", lambda *a, **k: None)

    nodes.generate_initial_answer(
        {
            "query": "灵境是什么",
            "retrieved_memories": [],
            "history": [],
            "linkin_context": {
                "active": True,
                "summary": "【靈境世界觀憲法】測試摘要",
                "system_overlay": "你正在協助「靈境·Linkin」。",
            },
        }
    )
    assert "測試摘要" in captured["prompt"]
    assert "靈境·Linkin" in captured["system"]
