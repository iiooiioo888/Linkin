"""雙跑：shadow／enabled 敏感零副作用；disabled 在敏感動作上停在審批。"""

from __future__ import annotations

from guardrail_service import reset_state as reset_guard
from tool_gateway import alert_rows, invoke
from tool_gateway import reset_state as reset_tools

from backend.company.tools import ToolCallRequest, ToolRegistry
from linkin_core.contracts.signatures import reset_nonce_store


def test_shadow_keeps_legacy_result_and_records_sensitive_gap(monkeypatch):
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    monkeypatch.setenv("TOOL_DUAL_RUN", "shadow")
    monkeypatch.setenv("TOOL_DUAL_RUN_EXECUTE_NEW", "0")
    reset_guard()
    reset_tools()
    reset_nonce_store()
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


def test_shadow_sensitive_zero_side_effects_even_if_execute_flag_on(monkeypatch):
    """shadow + EXECUTE_NEW=1 時敏感仍不得打適配器。"""
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    monkeypatch.setenv("TOOL_DUAL_RUN", "shadow")
    monkeypatch.setenv("TOOL_DUAL_RUN_EXECUTE_NEW", "1")
    reset_guard()
    reset_tools()
    reset_nonce_store()
    adapter_hits = {"n": 0}

    def minecraft(tool, args, token):
        adapter_hits["n"] += 1
        return {"ok": True, "tool": tool}

    def reject(*_a, **_k):
        adapter_hits["n"] += 1
        return {"ok": False}

    from tool_gateway import execute_new_path

    assert execute_new_path("shadow", "place_block") is False
    result = invoke(
        "place_block",
        {"x": 1},
        {"tenant_id": "acme", "trace_id": "t-shadow"},
        adapters={
            "minecraft": minecraft,
            "opc_write": reject,
            "opc_read": reject,
            "local": reject,
        },
        execute=execute_new_path("shadow", "place_block"),
    )
    assert adapter_hits["n"] == 0
    assert result.get("error_code") == "guardrail_confirm" or (
        isinstance(result.get("result"), dict) and result["result"].get("dry_run")
    )


def test_enabled_sensitive_only_dry_run(monkeypatch):
    """enabled 下敏感工具只做護欄 dry-run，不調 8081／minecraft。"""
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    monkeypatch.setenv("TOOL_DUAL_RUN", "enabled")
    monkeypatch.setenv("TOOL_DUAL_RUN_EXECUTE_NEW", "1")
    reset_guard()
    reset_tools()
    reset_nonce_store()
    adapter_hits = {"n": 0}

    def opc_write(tool, args, token):
        adapter_hits["n"] += 1
        return {"ok": True, "side_effect": True}

    def reject(*_a, **_k):
        adapter_hits["n"] += 1
        return {"ok": False}

    from tool_gateway import execute_new_path

    assert execute_new_path("enabled", "opc_write") is False
    result = invoke(
        "opc_write",
        {"node_id": "Valve", "value": 1},
        {"tenant_id": "acme", "trace_id": "t-enabled"},
        adapters={
            "opc_write": opc_write,
            "opc_read": reject,
            "minecraft": reject,
            "local": reject,
        },
        execute=execute_new_path("enabled", "opc_write"),
    )
    assert adapter_hits["n"] == 0
    assert result.get("error_code") == "guardrail_confirm" or (
        isinstance(result.get("result"), dict) and result["result"].get("dry_run")
    )


def test_disabled_sensitive_stops_before_legacy(monkeypatch):
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    monkeypatch.setenv("TOOL_DUAL_RUN", "disabled")
    reset_guard()
    reset_tools()
    reset_nonce_store()
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
