"""雙跑：shadow 回舊結果；disabled 在敏感動作上停在審批。"""

from __future__ import annotations

from guardrail_service import reset_state as reset_guard
from tool_gateway import alert_rows
from tool_gateway import reset_state as reset_tools

from backend.company.tools import ToolCallRequest, ToolRegistry


def test_shadow_keeps_legacy_result_and_records_sensitive_gap(monkeypatch):
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    monkeypatch.setenv("TOOL_DUAL_RUN", "shadow")
    monkeypatch.setenv("TOOL_DUAL_RUN_EXECUTE_NEW", "0")
    reset_guard()
    reset_tools()
    registry = ToolRegistry()
    calls = {"n": 0}

    def _place(**_kwargs):
        calls["n"] += 1
        return "placed"

    registry.register("place_block", "放方塊", {}, _place)
    outcome = registry.execute(ToolCallRequest("place_block", {"x": 1}))
    assert outcome.success is True
    assert outcome.result == "placed"
    assert calls["n"] == 1
    alerts = alert_rows()
    assert alerts
    assert alerts[0]["explainable"] is True
    assert alerts[0]["sensitive"] is True


def test_disabled_sensitive_stops_before_legacy(monkeypatch):
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    monkeypatch.setenv("TOOL_DUAL_RUN", "disabled")
    reset_guard()
    reset_tools()
    registry = ToolRegistry()
    calls = {"n": 0}

    def _place(**_kwargs):
        calls["n"] += 1
        return "placed"

    registry.register("place_block", "放方塊", {}, _place)
    outcome = registry.execute(ToolCallRequest("place_block", {"x": 1}))
    assert outcome.success is False
    assert calls["n"] == 0
    assert "審批" in outcome.error
