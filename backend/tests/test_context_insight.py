"""Context 洞察聚合測試（dsh-context 風格組成／趨勢／事件）。"""

from __future__ import annotations

import pytest

from backend.services.context_insight import COMPOSITION_KEYS, build_context_insight, resolve_default_task_id
from backend.services.trace_logger import TraceLogger


@pytest.fixture
def trace_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_TRACE_DIR", str(tmp_path))
    return tmp_path


def test_build_context_insight_composition_and_trend(trace_env):
    t = TraceLogger("ctx_demo")
    t.log_phase_change("analyze", data={"from_phase": "perceive", "reason": "advance"})
    t.log_context_injection(source="memos", items=["偏好：繁中", "約束：顯式啟用"], query="任務目標")
    t.log_llm_call(
        prompt="請摘要 [memos] 偏好：繁中",
        response="已記錄偏好。",
        model="qwen-turbo",
        system="你是助手",
        phase="analyze",
        role="executor",
        cost=0.001,
        duration_ms=120,
    )
    t.log_tool_call(tool="search", args={"q": "x", "hits": 3}, result="hit", phase="analyze")
    t.log_tool_call(
        tool="write_file",
        args={"path": "src/demo.ts", "new_string": "a\nb\nc\n", "old_string": "a\n"},
        result="ok",
        phase="analyze",
    )
    t.log_memory_operation(operation="prune", text="drop stale", phase="analyze")
    t.log_llm_call(
        prompt="第二步追問",
        response="繼續。",
        model="qwen-turbo",
        system="你是助手",
        phase="analyze",
        role="executor",
        cost=0.0005,
        duration_ms=80,
    )
    # 第三步刻意縮小窗口，觸發 compact 啟發式
    t.log_llm_call(
        prompt="短",
        response="ok",
        model="qwen-turbo",
        system="s",
        phase="analyze",
        role="reviewer",
        cost=0.0001,
        duration_ms=40,
    )

    insight = build_context_insight("ctx_demo")
    assert insight["task_id"] == "ctx_demo"
    assert insight["stats"]["llm_calls"] == 3
    assert insight["stats"]["context_injections"] == 1
    assert insight["stats"]["tool_calls"] == 2
    assert insight["stats"]["prunes"] >= 1
    assert set(insight["composition_keys"]) == set(COMPOSITION_KEYS)
    assert insight["composition"]["injected"]["tokens"] > 0
    assert insight["composition"]["assistant"]["tokens"] > 0
    assert len(insight["trend"]) == 3
    assert any(m["kind"] == "inject" for m in insight["trend"][0]["marks"])
    kinds = {e["kind"] for e in insight["events"]}
    assert "inject" in kinds
    assert "switch" in kinds
    assert insight["browser"]["categories"]["system"]
    assert insight["browser"]["categories"]["user"]
    assert insight["browser"]["categories"]["injected"]
    assert insight["browser"]["categories"]["tools"]
    tool_sources = {i["source"] for i in insight["browser"]["categories"]["tools"]}
    assert any(s.startswith("tool:") for s in tool_sources)
    assert insight["browser"]["vs_previous"] is not None
    assert insight["browser"]["vs_previous"]["prev_step"] == 1
    assert insight["browser"]["brief"]["model"] == "qwen-turbo"
    assert insight["stats"]["timing"]["llm_ms"] > 0
    assert insight["file_activity"]
    paths = {f["path"] for f in insight["file_activity"]}
    assert "src/demo.ts" in paths or any("demo.ts" in p for p in paths)
    roles = {a["role"] for a in insight["agent_network"]}
    assert "executor" in roles
    assert "reviewer" in roles
    assert "delta_bars" in insight["trend"][0]
    # 同 phase 的三步在 Turn 語意下應可被前端合併（後端仍輸出逐步 trend）
    assert all(row["phase"] == "analyze" for row in insight["trend"])


def test_context_insight_no_audit_score_fields(trace_env):
    """C-UI-004：Context 洞察不得攜帶審計分數槽位。"""
    t = TraceLogger("ctx_no_score")
    t.log_llm_call(prompt="hi", response="yo", model="m", system="s", phase="p")
    insight = build_context_insight("ctx_no_score")
    blob = str(insight)
    assert "audit_score" not in blob
    assert "audit_grade" not in blob
    assert "score" not in insight.get("stats", {})



def test_build_context_insight_empty_task(trace_env):
    insight = build_context_insight("missing")
    assert insight["stats"]["llm_calls"] == 0
    assert insight["selected_step"] is None
    assert insight["browser"]["categories"]["injected"]


def test_resolve_default_task_id(trace_env):
    assert resolve_default_task_id(None) is None
    TraceLogger("latest_one").log_llm_call(prompt="a", response="b", model="m")
    assert resolve_default_task_id(None) == "latest_one"
    assert resolve_default_task_id("  explicit  ") == "explicit"
