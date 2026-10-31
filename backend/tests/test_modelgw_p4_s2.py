"""P4-S2：C4 硬閘不漏上游／C5 錯誤碼／G-MAP1 覆蓋率閘（WIRE=enforce 契約；不改碼預設）。"""

from __future__ import annotations

import json

import pytest

from backend.modelgw.errors import (
    CODE_ADMISSION,
    CODE_PROVISIONING,
    CODE_UNSUPPORTED,
    REASON_TRC,
    ModelGWError,
)
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
            _rec("trc-bad", trust_remote_code=True),
        ]
    )
    reset_service(ModelGWService(registry=reg))
    yield
    reset_service(None)


# --- C6 持續：碼預設仍 off ---


def test_s2_c6_wire_default_still_off(monkeypatch) -> None:
    monkeypatch.delenv("MODELGW_WIRE_MODE", raising=False)
    assert wire_mode() == "off"


# --- C4：enforce 下未 admit 不得打上游（漏＝fail）---


def test_s2_c4_call_llm_unsupported_no_upstream_leak(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    leaks: list[str] = []

    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "no-such")],
    )

    def on_route(*a, **k):
        leaks.append("upstream")
        return "leaked"

    monkeypatch.setattr("backend.core.llm._call_llm_on_route", on_route)
    from backend.core.llm import _call_llm_core

    with pytest.raises(ModelGWError) as ei:
        _call_llm_core("hi", model="no-such")
    assert ei.value.code == CODE_UNSUPPORTED
    assert ei.value.http_hint == 400
    assert leaks == []


def test_s2_c4_call_llm_provisioning_no_upstream_leak(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    leaks: list[str] = []
    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "warming")],
    )
    def _track_upstream(*a, **k):
        leaks.append("upstream")
        return "x"

    monkeypatch.setattr("backend.core.llm._call_llm_on_route", _track_upstream)
    from backend.core.llm import _call_llm_core

    with pytest.raises(ModelGWError) as ei:
        _call_llm_core("hi", model="warming")
    assert ei.value.code == CODE_PROVISIONING
    assert ei.value.http_hint == 503
    assert leaks == []


def test_s2_c4_call_llm_admission_rejected_no_upstream_leak(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    leaks: list[str] = []
    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, "trc-bad")],
    )
    def _track_upstream(*a, **k):
        leaks.append("upstream")
        return "x"

    monkeypatch.setattr("backend.core.llm._call_llm_on_route", _track_upstream)
    from backend.core.llm import _call_llm_core

    with pytest.raises(ModelGWError) as ei:
        _call_llm_core("hi", model="trc-bad")
    assert ei.value.code == CODE_ADMISSION
    assert ei.value.http_hint == 400
    assert ei.value.reason == REASON_TRC
    assert leaks == []


def test_s2_c4_call_llm_stream_unsupported_no_upstream_leak(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    leaks: list[str] = []

    def fake_completion(**kwargs):
        leaks.append("upstream")
        return []

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

    with pytest.raises(ModelGWError) as ei:
        list(call_llm_stream("hi", model="no-such"))
    assert ei.value.code == CODE_UNSUPPORTED
    assert leaks == []


def test_s2_c4_hub_llm_probe_unmapped_no_upstream_leak(monkeypatch, gw) -> None:
    """Hub entry=_llm_probe：表內空映射 → UNSUPPORTED；不得打上游。"""
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.setenv("MODELGW_HUB_ID_MAP", '{"gpt-5.6-sol": ""}')
    from backend.modelgw.hub_id_map import reset_hub_id_map_cache

    reset_hub_id_map_cache()
    leaks: list[str] = []

    def on_route(*a, **k):
        leaks.append("upstream")
        return "leaked"

    monkeypatch.setattr("backend.core.llm._build_call_hops", lambda *a, **k: [(None, "gpt-5.6-sol")])
    monkeypatch.setattr("backend.core.llm._call_llm_on_route", on_route)

    from backend.hub.service import _llm_probe

    with pytest.raises(ModelGWError) as ei:
        _llm_probe("hi", None, "gpt-5.6-sol")
    assert ei.value.code == CODE_UNSUPPORTED
    assert leaks == []


def test_s2_c4_hub_failover_preserves_modelgw_error(monkeypatch, gw) -> None:
    """Failover 全鏈 ModelGW 拒 → 仍拋 ModelGWError（C5 碼），非 HubUpstreamError 503。"""
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.setenv(
        "MODELGW_HUB_ID_MAP",
        json.dumps({"gpt-5.6-sol": "", "gemini-3.1-pro": "", "mercury-2": ""}),
    )
    from backend.modelgw.hub_id_map import reset_hub_id_map_cache

    reset_hub_id_map_cache()
    leaks: list[str] = []

    def probe(prompt: str, system=None, model: str = "", **kwargs):
        # 走真實 call_llm → precheck
        from backend.core.llm import call_llm

        return call_llm(prompt, system=system, model=model, **kwargs)

    monkeypatch.setattr(
        "backend.core.llm._build_call_hops",
        lambda *a, **k: [(None, a[1] if len(a) > 1 else k.get("model"))],
    )
    def _track_upstream(*a, **k):
        mid = k.get("model") or (a[2] if len(a) > 2 else "?")
        leaks.append(str(mid))
        return "x"

    monkeypatch.setattr("backend.core.llm._call_llm_on_route", _track_upstream)

    from backend.hub.router import HubUpstreamError, invoke_with_failover

    with pytest.raises(ModelGWError) as ei:
        invoke_with_failover(
            probe,
            [{"role": "user", "content": "hi"}],
            primary="gpt-5.6-sol",
            region="US",
            whitelist=["gpt-5.6-sol", "gemini-3.1-pro"],
            sleeper=lambda _s: None,
        )
    assert ei.value.code == CODE_UNSUPPORTED
    assert leaks == []
    assert not isinstance(ei.value, HubUpstreamError)


# --- C5：熱路徑暴露 ModelGW code＋http class ---


def test_s2_c5_codes_http_hint_matrix(monkeypatch, gw) -> None:
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    from backend.modelgw.runtime import precheck_model

    with pytest.raises(ModelGWError) as u:
        precheck_model("no-such")
    assert u.value.code == CODE_UNSUPPORTED and u.value.http_hint == 400

    with pytest.raises(ModelGWError) as p:
        precheck_model("warming")
    assert p.value.code == CODE_PROVISIONING and p.value.http_hint == 503

    with pytest.raises(ModelGWError) as a:
        precheck_model("trc-bad")
    assert a.value.code == CODE_ADMISSION and a.value.http_hint == 400


def test_s2_c5_hub_api_maps_modelgw_problem(monkeypatch, gw) -> None:
    from backend.hub.api import modelgw_problem_response
    from backend.modelgw.errors import ModelGWError as E

    resp = modelgw_problem_response(E(CODE_UNSUPPORTED, "x", http_hint=400))
    assert resp.status_code == 400
    assert resp.body  # type: ignore[attr-defined]
    body = json.loads(bytes(resp.body).decode())
    assert body["code"] == CODE_UNSUPPORTED

    resp2 = modelgw_problem_response(E(CODE_PROVISIONING, "warming", http_hint=503))
    assert resp2.status_code == 503
    body2 = json.loads(bytes(resp2.body).decode())
    assert body2["code"] == CODE_PROVISIONING
    assert "Retry-After" in resp2.headers


def test_s2_c5_to_problem_exposes_code() -> None:
    err = ModelGWError(CODE_ADMISSION, "denied", reason=REASON_TRC, http_hint=400)
    body = err.to_problem()
    assert body["code"] == CODE_ADMISSION
    assert body["status"] == 400
    assert body["reason"] == REASON_TRC


# --- G-MAP1：覆蓋率閘（fixture only；不填生產 json）---


def test_s2_gmap1_coverage_empty_static_shape(monkeypatch) -> None:
    """生產形狀：靜態鍵全空 → coverage 0；claim 不許。"""
    monkeypatch.setenv(
        "MODELGW_HUB_ID_MAP",
        json.dumps({"gpt-5.6-sol": "", "gemini-3.1-pro": "TBD", "mimo-v2.5-pro": None}),
    )
    from backend.modelgw.hub_id_map import (
        hub_id_map_coverage,
        hub_unified_claim_allowed,
        reset_hub_id_map_cache,
    )

    reset_hub_id_map_cache()
    cov = hub_id_map_coverage()
    assert cov["total"] == 3
    assert cov["filled"] == 0
    assert cov["empty"] == 3
    assert cov["coverage_ratio"] == 0.0
    assert hub_unified_claim_allowed() is False


def test_s2_gmap1_claim_allowed_when_100_percent_filled(monkeypatch) -> None:
    monkeypatch.setenv(
        "MODELGW_HUB_ID_MAP",
        json.dumps({"gpt-5.6-sol": "ready-a", "gemini-3.1-pro": "ready-b"}),
    )
    from backend.modelgw.hub_id_map import (
        hub_id_map_coverage,
        hub_unified_claim_allowed,
        reset_hub_id_map_cache,
    )

    reset_hub_id_map_cache()
    cov = hub_id_map_coverage()
    assert cov["filled"] == 2 and cov["empty"] == 0
    assert hub_unified_claim_allowed() is True


def test_s2_gmap1_claim_allowed_with_explicit_sunset(monkeypatch) -> None:
    monkeypatch.setenv(
        "MODELGW_HUB_ID_MAP",
        json.dumps(
            {
                "map": {"gpt-5.6-sol": "ready-a", "gemini-3.1-pro": "", "mercury-2": ""},
                "sunset": {
                    "gemini-3.1-pro": {"status": "deprecated", "note": "fixture"},
                    "mercury-2": {"status": "sunset"},
                },
            }
        ),
    )
    from backend.modelgw.hub_id_map import (
        hub_unified_claim_allowed,
        reset_hub_id_map_cache,
    )

    reset_hub_id_map_cache()
    assert hub_unified_claim_allowed() is True


def test_s2_gmap1_claim_denied_if_empty_without_sunset(monkeypatch) -> None:
    monkeypatch.setenv(
        "MODELGW_HUB_ID_MAP",
        json.dumps(
            {
                "map": {"gpt-5.6-sol": "ready-a", "gemini-3.1-pro": ""},
                "sunset": {"gpt-5.6-sol": {"status": "deprecated"}},  # 填實鍵的 sunset 無關
            }
        ),
    )
    from backend.modelgw.hub_id_map import hub_unified_claim_allowed, reset_hub_id_map_cache

    reset_hub_id_map_cache()
    assert hub_unified_claim_allowed() is False


def test_s2_gmap1_production_file_still_empty_keys(monkeypatch) -> None:
    """硬禁核對：預設 hub_id_map.json 不得被本波填入真實 Registry ID。"""
    from pathlib import Path

    from backend.modelgw.hub_id_map import (
        hub_id_map_coverage,
        hub_unified_claim_allowed,
        reset_hub_id_map_cache,
    )

    monkeypatch.delenv("MODELGW_HUB_ID_MAP", raising=False)
    monkeypatch.delenv("MODELGW_HUB_ID_MAP_PATH", raising=False)
    reset_hub_id_map_cache()
    path = Path(__file__).resolve().parents[1] / "modelgw" / "hub_id_map.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert all(not (v or "").strip() or str(v).upper() == "TBD" for v in data["map"].values())
    cov = hub_id_map_coverage()
    assert cov["filled"] == 0
    assert hub_unified_claim_allowed() is False
