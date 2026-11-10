"""P5/#134：admit／route／precheck／HTTP chat 接 get_for_tenant（A1–A6）。"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modelgw.admission import AdmitDecision, admit, lookup_record
from backend.modelgw.api import register_modelgw
from backend.modelgw.errors import CODE_UNSUPPORTED, ModelGWError
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus
from backend.modelgw.runtime import precheck_model, reset_service, wire_mode
from backend.modelgw.service import ModelGWService
from backend.modelgw.sql_registry import SqliteRegistry


def _rec(model_id: str, status: ModelStatus = ModelStatus.READY, **kw: Any) -> ModelRecord:
    fields: dict[str, Any] = {
        "model_id": model_id,
        "revision": "r1",
        "status": status,
        "license": "Apache-2.0",
        "trust_remote_code": False,
        "plane": "cloud",
    }
    fields.update(kw)
    return ModelRecord(
        model_id=str(fields["model_id"]),
        revision=str(fields["revision"]),
        endpoint=str(fields.get("endpoint") or ""),
        runtime=str(fields.get("runtime") or "cloud"),
        provider=str(fields.get("provider") or "cloud"),
        gpu_type=str(fields.get("gpu_type") or ""),
        lease_id=str(fields.get("lease_id") or ""),
        replicas=int(fields.get("replicas") or 1),
        created_at=float(fields.get("created_at") or 0.0),
        last_used_at=float(fields.get("last_used_at") or 0.0),
        ttl=fields.get("ttl"),
        status=fields["status"]
        if isinstance(fields["status"], ModelStatus)
        else ModelStatus(str(fields["status"])),
        license=str(fields.get("license") or "Apache-2.0"),
        trust_remote_code=bool(fields.get("trust_remote_code", False)),
        gated=bool(fields.get("gated", False)),
        gated_approved=bool(fields.get("gated_approved", False)),
        checksum=fields.get("checksum"),
        plane=str(fields.get("plane") or "cloud"),
        extras=dict(fields["extras"]) if isinstance(fields.get("extras"), dict) else {},
    )


@pytest.fixture()
def sql_reg(tmp_path: Path) -> Generator[SqliteRegistry, None, None]:
    reg = SqliteRegistry(str(tmp_path / "p5-admit.sqlite3"))
    yield reg
    reg.close()


@pytest.fixture()
def seeded(sql_reg: SqliteRegistry) -> SqliteRegistry:
    """acme 有 READY；"" 有另一 revision READY；other 無列。"""
    sql_reg.upsert(_rec("shared-m", revision="acme-rev"), tenant_id="acme")
    sql_reg.upsert(_rec("shared-m", revision="empty-rev"), tenant_id="")
    return sql_reg


# --- A1：同 tenant ALLOW ---
class TestA1AdmitSameTenant:
    def test_admit_acme_allow(self, seeded: SqliteRegistry) -> None:
        r = admit("shared-m", seeded, tenant_id="acme")
        assert r.decision == AdmitDecision.ALLOW
        assert r.record is not None
        assert r.record.revision == "acme-rev"

    def test_service_admit_acme(self, seeded: SqliteRegistry) -> None:
        svc = ModelGWService(registry=seeded)
        result = svc.admit_or_raise("shared-m", tenant_id="acme")
        assert result.allowed
        assert result.record is not None
        assert result.record.revision == "acme-rev"


# --- A2：異 tenant 缺列 → UNSUPPORTED；不回落 ---
class TestA2NoFallback:
    def test_other_unsupported(self, seeded: SqliteRegistry) -> None:
        r = admit("shared-m", seeded, tenant_id="other")
        assert r.decision == AdmitDecision.REJECT
        assert r.code == CODE_UNSUPPORTED
        assert r.record is None

    def test_lookup_does_not_fall_back(self, seeded: SqliteRegistry) -> None:
        assert lookup_record(seeded, "shared-m", tenant_id="other") is None
        # 確認 acme／"" 列仍在，證明沒有被誤讀
        assert lookup_record(seeded, "shared-m", tenant_id="acme") is not None
        assert lookup_record(seeded, "shared-m", tenant_id="") is not None

    def test_service_other_raises(self, seeded: SqliteRegistry) -> None:
        svc = ModelGWService(registry=seeded)
        with pytest.raises(ModelGWError) as ei:
            svc.admit_or_raise("shared-m", tenant_id="other")
        assert ei.value.code == CODE_UNSUPPORTED


# --- A3：省略／"" 與現網一致 ---
class TestA3EmptyTenantCompat:
    def test_omit_hits_empty_tenant(self, seeded: SqliteRegistry) -> None:
        r = admit("shared-m", seeded)  # 預設 ""
        assert r.decision == AdmitDecision.ALLOW
        assert r.record is not None
        assert r.record.revision == "empty-rev"

    def test_explicit_empty(self, seeded: SqliteRegistry) -> None:
        r = admit("shared-m", seeded, tenant_id="")
        assert r.allowed
        assert r.record is not None
        assert r.record.revision == "empty-rev"


# --- A4：route／chat／precheck 帶非空 tenant 同結果 ---
class TestA4RouteChatPrecheck:
    def test_route_acme_ok(self, seeded: SqliteRegistry) -> None:
        svc = ModelGWService(registry=seeded)
        plan = svc.route("shared-m", tenant_id="acme")
        assert plan.primary == "shared-m"

    def test_route_other_unsupported(self, seeded: SqliteRegistry) -> None:
        svc = ModelGWService(registry=seeded)
        with pytest.raises(ModelGWError) as ei:
            svc.route("shared-m", tenant_id="other")
        assert ei.value.code == CODE_UNSUPPORTED

    def test_invoke_chat_acme(self, seeded: SqliteRegistry) -> None:
        svc = ModelGWService(registry=seeded)
        calls: list[str] = []

        def llm(**kwargs: Any) -> str:
            calls.append(str(kwargs.get("model") or ""))
            return "ok"

        out = svc.invoke_chat(
            "shared-m",
            [{"role": "user", "content": "hi"}],
            llm,
            tenant_id="acme",
        )
        assert out.text == "ok"
        assert out.model_id == "shared-m"
        assert calls == ["shared-m"]

    def test_invoke_chat_other_zero_upstream(self, seeded: SqliteRegistry) -> None:
        svc = ModelGWService(registry=seeded)
        calls: list[str] = []

        def llm(**kwargs: Any) -> str:
            calls.append("hit")
            return "x"

        with pytest.raises(ModelGWError) as ei:
            svc.invoke_chat(
                "shared-m",
                [{"role": "user", "content": "hi"}],
                llm,
                tenant_id="other",
            )
        assert ei.value.code == CODE_UNSUPPORTED
        assert calls == []

    def test_precheck_tenant(self, seeded: SqliteRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_service(ModelGWService(registry=seeded))
        monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
        try:
            precheck_model("shared-m", tenant_id="acme")  # 不應拋
            with pytest.raises(ModelGWError) as ei:
                precheck_model("shared-m", tenant_id="other")
            assert ei.value.code == CODE_UNSUPPORTED
        finally:
            reset_service(None)

    def test_http_admit_and_chat(self, seeded: SqliteRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_service(ModelGWService(registry=seeded))
        monkeypatch.setenv("MODELGW_WIRE_MODE", "off")
        app = FastAPI()
        register_modelgw(app)
        try:
            with TestClient(app) as client:
                ok = client.post(
                    "/modelgw/v1/admit",
                    json={"model_id": "shared-m", "tenant_id": "acme"},
                )
                assert ok.status_code == 200
                assert ok.json()["decision"] == "ALLOW"
                assert ok.json()["tenant_id"] == "acme"

                bad = client.post(
                    "/modelgw/v1/admit",
                    json={"model_id": "shared-m", "tenant_id": "other"},
                )
                assert bad.status_code == 400
                assert bad.json()["code"] == CODE_UNSUPPORTED

                # chat：注入 llm 會走 call_llm；改為測 route 層已覆蓋。
                # 此處驗 body tenant 下傳：異租戶應 400 且不觸發上游。
                chat_bad = client.post(
                    "/modelgw/v1/chat/completions",
                    json={
                        "model": "shared-m",
                        "tenant_id": "other",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                assert chat_bad.status_code == 400
                assert chat_bad.json()["code"] == CODE_UNSUPPORTED
        finally:
            reset_service(None)


# --- A5：InMemory get_for_tenant 不炸；單平面 ---
class TestA5InMemorySinglePlane:
    def test_get_for_tenant_equals_get(self) -> None:
        reg = InMemoryRegistry([_rec("m1")])
        assert reg.get_for_tenant("acme", "m1") is not None
        assert reg.get_for_tenant("other", "m1") is not None
        assert reg.get_for_tenant("", "m1") is not None
        assert reg.get_for_tenant("any", "missing") is None
        # admit 透過 duck-type 也走單平面
        assert admit("m1", reg, tenant_id="acme").allowed
        assert admit("m1", reg, tenant_id="other").allowed


# --- A6：WIRE 預設 off；shadow log 帶 tenant_id ---
class TestA6WireAndShadowLog:
    def test_wire_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MODELGW_WIRE_MODE", raising=False)
        assert wire_mode() == "off"

    def test_shadow_log_includes_tenant(
        self, seeded: SqliteRegistry, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        reset_service(ModelGWService(registry=seeded))
        monkeypatch.setenv("MODELGW_WIRE_MODE", "shadow")
        try:
            with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
                precheck_model("shared-m", tenant_id="other")
            assert any(
                "tenant_id=other" in r.message and "MODELGW shadow" in r.message
                for r in caplog.records
            )
        finally:
            reset_service(None)

    def test_call_llm_precheck_fixed_empty_tenant(
        self, seeded: SqliteRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Q8：call_llm／WIRE 無來源 → 固定 ""（命中空租戶列）。"""
        reset_service(ModelGWService(registry=seeded))
        monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
        try:
            # 預設 tenant="" → 命中 empty-rev 列
            precheck_model("shared-m")
        finally:
            reset_service(None)
