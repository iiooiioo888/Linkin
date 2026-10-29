"""ModelGW 準入契約：MGW-R1／R2／R3 與 O18 骨架。"""

from __future__ import annotations

import pytest

from backend.modelgw.admission import AdmissionPolicy, AdmitDecision, admit
from backend.modelgw.errors import (
    CODE_ADMISSION,
    CODE_NOT_READY,
    CODE_PROVISIONING,
    CODE_UNSUPPORTED,
    REASON_GATE,
    REASON_LICENSE,
    REASON_REVISION_MAIN,
    REASON_TRC,
    ModelGWError,
)
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus
from backend.modelgw.service import ModelGWService


def _ready(**kwargs) -> ModelRecord:
    base = {
        "model_id": "m1",
        "revision": "rev1",
        "status": ModelStatus.READY,
        "license": "Apache-2.0",
        "trust_remote_code": False,
        "gated": False,
    }
    base.update(kwargs)
    return ModelRecord(**base)


def test_mgw_r1_missing_model_zero_upstream() -> None:
    reg = InMemoryRegistry()
    calls: list[str] = []

    def llm(**kwargs):
        calls.append("hit")
        return "x"

    svc = ModelGWService(registry=reg)
    with pytest.raises(ModelGWError) as ei:
        svc.invoke_chat("no-such", [{"role": "user", "content": "hi"}], llm)
    assert ei.value.code == CODE_UNSUPPORTED
    assert ei.value.http_hint == 400
    assert calls == []


def test_mgw_r2_provisioning_zero_upstream() -> None:
    reg = InMemoryRegistry(
        [_ready(model_id="warming", status=ModelStatus.PROVISIONING)]
    )
    calls: list[str] = []
    svc = ModelGWService(registry=reg)
    with pytest.raises(ModelGWError) as ei:
        svc.invoke_chat("warming", [{"role": "user", "content": "hi"}], lambda **k: calls.append("x") or "ok")
    assert ei.value.code == CODE_PROVISIONING
    assert ei.value.http_hint == 503
    assert calls == []
    r = admit("warming", reg)
    assert r.decision == AdmitDecision.PROVISIONING


def test_mgw_r3_trust_remote_code_denied() -> None:
    reg = InMemoryRegistry([_ready(trust_remote_code=True)])
    r = admit("m1", reg)
    assert r.decision == AdmitDecision.REJECT
    assert r.code == CODE_ADMISSION
    assert r.reason == REASON_TRC

    svc = ModelGWService(registry=reg)
    calls: list[str] = []
    with pytest.raises(ModelGWError) as ei:
        svc.invoke_chat("m1", [{"role": "user", "content": "hi"}], lambda **k: calls.append("x") or "ok")
    assert ei.value.code == CODE_ADMISSION
    assert calls == []


def test_o18_revision_main_forbidden() -> None:
    reg = InMemoryRegistry([_ready(revision="main")])
    r = admit("m1", reg)
    assert r.reason == REASON_REVISION_MAIN


def test_o18_license_not_allowlisted() -> None:
    reg = InMemoryRegistry([_ready(license="Proprietary-Evil")])
    r = admit("m1", reg)
    assert r.reason == REASON_LICENSE


def test_o18_gated_skeleton() -> None:
    reg = InMemoryRegistry([_ready(gated=True, gated_approved=False)])
    r = admit("m1", reg)
    assert r.reason == REASON_GATE
    reg.upsert(_ready(gated=True, gated_approved=True))
    assert admit("m1", reg).allowed


def test_failed_status_not_ready() -> None:
    reg = InMemoryRegistry([_ready(status=ModelStatus.FAILED)])
    r = admit("m1", reg)
    assert r.code == CODE_NOT_READY


def test_checksum_skipped_by_default() -> None:
    reg = InMemoryRegistry([_ready(checksum=None)])
    assert admit("m1", reg).allowed
    denied = admit("m1", reg, AdmissionPolicy(verify_checksum=True))
    assert not denied.allowed
