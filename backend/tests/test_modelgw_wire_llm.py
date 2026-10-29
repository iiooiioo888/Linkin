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
    assert any("MODELGW shadow" in r.message for r in caplog.records)


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
