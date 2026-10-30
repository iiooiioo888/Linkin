"""ModelGW → call_llm 掛載：off／shadow／enforce 行為。"""

from __future__ import annotations

import logging

import pytest

from backend.modelgw.errors import CODE_PROVISIONING, CODE_UNSUPPORTED, ModelGWError
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus
from backend.modelgw.runtime import reset_service, wire_mode
from backend.modelgw.service import ModelGWService


def _rec(model_id: str, status=ModelStatus.READY, **kw) -> ModelRecord:
    base = {
        "model_id": model_id,
        "revision": "r1",
        "status": status,
        "license": "Apache-2.0",
        "trust_remote_code": False,
        "plane": "cloud",
    }
    base.update(kw)
    return ModelRecord(**base)


@pytest.fixture()
def gw(monkeypatch):
    reg = InMemoryRegistry(
        [
            _rec("ready-a"),
            _rec("warming", status=ModelStatus.PROVISIONING),
        ]
    )
    reset_service(ModelGWService(registry=reg))
    yield
    reset_service(None)


def test_wire_mode_default_off(monkeypatch, gw) -> None:
    monkeypatch.delenv("MODELGW_WIRE_MODE", raising=False)
    assert wire_mode() == "off"


def test_call_llm_off_skips_gate(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "off")
    calls: list[str] = []

    def fake_core(*args, **kwargs):
        calls.append("ok")
        return "ok"

    monkeypatch.setattr("backend.core.llm._call_llm_on_route", fake_core)
    # 還需繞過 hops 建構；直接測 precheck 路徑：呼叫 _call_llm_core
    from backend.core.llm import _call_llm_core

    # unknown model — off 模式不得拋 ModelGWError
    # 但 _call_llm_core 會真的走 litellm；改 patch 整段 on_route 與 build hops
    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "no-such")],
    )

    def on_route(*args, **kwargs):
        calls.append(kwargs.get("model") or args[2] if len(args) > 2 else "x")
        return "ok"

    monkeypatch.setattr("backend.core.llm._call_llm_on_route", on_route)
    out = _call_llm_core("hi", model="no-such")
    assert out == "ok"
    assert calls


def test_call_llm_enforce_blocks_unsupported(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    from backend.core.llm import _call_llm_core

    with pytest.raises(ModelGWError) as ei:
        _call_llm_core("hi", model="no-such")
    assert ei.value.code == CODE_UNSUPPORTED
    assert ei.value.http_hint == 400


def test_call_llm_enforce_provisioning(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    from backend.core.llm import _call_llm_core

    with pytest.raises(ModelGWError) as ei:
        _call_llm_core("hi", model="warming")
    assert ei.value.code == CODE_PROVISIONING
    assert ei.value.http_hint == 503


def test_call_llm_shadow_allows_but_logs(monkeypatch, gw, caplog) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "shadow")
    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "no-such")],
    )
    monkeypatch.setattr(
        "backend.core.llm._call_llm_on_route",
        lambda *a, **k: "shadow-ok",
    )
    from backend.core.llm import _call_llm_core

    with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
        out = _call_llm_core("hi", model="no-such")
    assert out == "shadow-ok"
    assert any("shadow admit blocked-would-be" in r.message for r in caplog.records)


def test_call_llm_enforce_allows_ready(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "ready-a")],
    )
    monkeypatch.setattr(
        "backend.core.llm._call_llm_on_route",
        lambda *a, **k: "ready-ok",
    )
    from backend.core.llm import _call_llm_core

    assert _call_llm_core("hi", model="ready-a") == "ready-ok"


# --- P4-S1：stream precheck／path 觀測／Hub ID map ---


def test_call_llm_stream_shadow_precheck_logs(monkeypatch, gw, caplog) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "shadow")
    from backend.modelgw.runtime import path_counts, reset_path_counts

    reset_path_counts()

    def fake_completion(**kwargs):
        class _Delta:
            content = "x"
            reasoning_content = None

        class _Choice:
            delta = _Delta()

        class _Chunk:
            choices = [_Choice()]

        return [_Chunk()]

    monkeypatch.setattr("backend.core.llm.completion", fake_completion)
    monkeypatch.setattr(
        "backend.core.llm._resolve_call_target",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "backend.core.llm._llm_params",
        lambda *a, **k: {"model": "no-such", "api_base": None},
    )
    monkeypatch.setattr("backend.core.llm.clamp_model", lambda m, **k: m or "no-such")
    monkeypatch.setattr("backend.core.llm._ensure_provider_prefix", lambda m: m)
    monkeypatch.setattr("backend.core.llm._openrouter_extra", lambda *a, **k: {})
    monkeypatch.setattr("backend.billing.metering.precheck_llm", lambda *a, **k: None)
    monkeypatch.setattr("backend.billing.metering.meter_llm", lambda *a, **k: None)

    from backend.core.llm import call_llm_stream

    with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
        out = "".join(call_llm_stream("hi", model="no-such"))
    assert out == "x"
    assert any("path=via" in r.message and "entry=stream" in r.message for r in caplog.records)
    assert any("shadow admit blocked-would-be" in r.message for r in caplog.records)
    assert path_counts()["via"] >= 1
    assert path_counts()["would_block"] >= 1


def test_call_llm_stream_off_bypass_log(monkeypatch, gw, caplog) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "off")
    from backend.modelgw.runtime import path_counts, reset_path_counts

    reset_path_counts()

    def fake_completion(**kwargs):
        class _Delta:
            content = "y"
            reasoning_content = None

        class _Choice:
            delta = _Delta()

        class _Chunk:
            choices = [_Choice()]

        return [_Chunk()]

    monkeypatch.setattr("backend.core.llm.completion", fake_completion)
    monkeypatch.setattr("backend.core.llm._resolve_call_target", lambda *a, **k: None)
    monkeypatch.setattr(
        "backend.core.llm._llm_params",
        lambda *a, **k: {"model": "no-such", "api_base": None},
    )
    monkeypatch.setattr("backend.core.llm.clamp_model", lambda m, **k: m or "no-such")
    monkeypatch.setattr("backend.core.llm._ensure_provider_prefix", lambda m: m)
    monkeypatch.setattr("backend.core.llm._openrouter_extra", lambda *a, **k: {})
    monkeypatch.setattr("backend.billing.metering.precheck_llm", lambda *a, **k: None)
    monkeypatch.setattr("backend.billing.metering.meter_llm", lambda *a, **k: None)

    from backend.core.llm import call_llm_stream

    with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
        out = "".join(call_llm_stream("hi", model="no-such"))
    assert out == "y"
    assert any("MODELGW path=bypass" in r.message and "entry=stream" in r.message for r in caplog.records)
    assert path_counts()["bypass"] >= 1


def test_call_llm_stream_enforce_blocks_unsupported(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    from backend.core.llm import call_llm_stream

    with pytest.raises(ModelGWError) as ei:
        list(call_llm_stream("hi", model="no-such"))
    assert ei.value.code == CODE_UNSUPPORTED


def test_hub_id_map_unmapped_shadow_shape(monkeypatch, gw, caplog) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "shadow")
    monkeypatch.setenv(
        "MODELGW_HUB_ID_MAP",
        '{"gpt-5.6-sol": "", "gemini-3.1-pro": "TBD"}',
    )
    from backend.modelgw.hub_id_map import reset_hub_id_map_cache
    from backend.modelgw.runtime import path_counts, precheck_model, reset_path_counts

    reset_hub_id_map_cache()
    reset_path_counts()
    with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
        precheck_model("gpt-5.6-sol", entry="hub")
    assert any(
        "code=UNSUPPORTED_MODEL" in r.message and "entry=hub" in r.message
        for r in caplog.records
    )
    assert path_counts()["would_block"] >= 1


def test_hub_id_map_unmapped_enforce_raises(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.setenv("MODELGW_HUB_ID_MAP", '{"gpt-5.6-sol": ""}')
    from backend.modelgw.hub_id_map import reset_hub_id_map_cache
    from backend.modelgw.runtime import precheck_model

    reset_hub_id_map_cache()
    with pytest.raises(ModelGWError) as ei:
        precheck_model("gpt-5.6-sol", entry="hub")
    assert ei.value.code == CODE_UNSUPPORTED


def test_hub_id_map_mapped_uses_registry_id(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.setenv("MODELGW_HUB_ID_MAP", '{"gpt-5.6-sol": "ready-a"}')
    from backend.modelgw.hub_id_map import reset_hub_id_map_cache
    from backend.modelgw.runtime import precheck_model

    reset_hub_id_map_cache()
    precheck_model("gpt-5.6-sol", entry="hub")  # ready-a 在 gw fixture


def test_hub_id_map_passthrough_non_hub_key(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.setenv("MODELGW_HUB_ID_MAP", '{"gpt-5.6-sol": ""}')
    from backend.modelgw.hub_id_map import reset_hub_id_map_cache
    from backend.modelgw.runtime import precheck_model

    reset_hub_id_map_cache()
    precheck_model("ready-a")  # 非表鍵 → 原樣 admit


def test_entry_scope_hub_on_call_llm(monkeypatch, gw, caplog) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "shadow")
    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "no-such")],
    )
    monkeypatch.setattr(
        "backend.core.llm._call_llm_on_route",
        lambda *a, **k: "ok",
    )
    from backend.core.llm import _call_llm_core
    from backend.modelgw.runtime import entry_scope, reset_path_counts

    reset_path_counts()
    with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
        with entry_scope("hub"):
            assert _call_llm_core("hi", model="no-such") == "ok"
    assert any("entry=hub" in r.message and "path=via" in r.message for r in caplog.records)


def test_wire_mode_default_unchanged_off(monkeypatch) -> None:
    """C6：不改 WIRE 預設碼值。"""
    monkeypatch.delenv("MODELGW_WIRE_MODE", raising=False)
    assert wire_mode() == "off"
