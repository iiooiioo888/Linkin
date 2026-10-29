"""P1/#130：SQL Registry＋部署回調驗收（A1–A8；SQLite 檔）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modelgw.api import register_modelgw
from backend.modelgw.callback import (
    CallbackConflict,
    assert_status_transition,
    process_deploy_callback,
    sign_body,
)
from backend.modelgw.errors import CODE_NOT_READY, CODE_PROVISIONING
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus
from backend.modelgw.runtime import build_registry, reset_service
from backend.modelgw.service import ModelGWService
from backend.modelgw.sql_registry import SqliteRegistry, parse_database_url

HMAC_KEY = "test-modelgw-callback-key-not-guardrail"


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


def _signed_headers(body: dict, key: str = HMAC_KEY, idem: str = "idem-1") -> dict[str, str]:
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "Content-Type": "application/json",
        "Idempotency-Key": idem,
        "X-ModelGW-Signature": sign_body(raw, key),
    }, raw


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "modelgw.sqlite3")


@pytest.fixture()
def sql_reg(db_path: str) -> SqliteRegistry:
    reg = SqliteRegistry(db_path)
    yield reg
    reg.close()


class TestParseUrl:
    def test_sqlite_abs(self) -> None:
        eng, path = parse_database_url("sqlite:////tmp/x.db")
        assert eng == "sqlite"
        assert path == "/tmp/x.db"

    def test_postgres_detected(self) -> None:
        eng, _ = parse_database_url("postgresql://u:p@localhost/db")
        assert eng == "postgres"


class TestStatusTransition:
    def test_provisioning_to_ready(self) -> None:
        assert_status_transition("PROVISIONING", "READY")

    def test_ready_to_terminating(self) -> None:
        assert_status_transition("READY", "TERMINATING")

    def test_same_status_lww(self) -> None:
        assert_status_transition("READY", "READY")

    def test_reject_ready_to_provisioning(self) -> None:
        with pytest.raises(CallbackConflict):
            assert_status_transition("READY", "PROVISIONING")

    def test_reject_terminating_to_ready(self) -> None:
        with pytest.raises(CallbackConflict):
            assert_status_transition("TERMINATING", "READY")


class TestA1RestartPersists:
    def test_seed_and_callback_survive_reopen(self, db_path: str) -> None:
        reg1 = SqliteRegistry(db_path)
        reg1.seed_if_empty(
            [_rec("warming-llama", status=ModelStatus.PROVISIONING, revision="def456")]
        )
        body = {
            "tenant_id": "",
            "model_id": "warming-llama",
            "outcome": "success",
            "status": "READY",
            "revision": "def456",
            "endpoint": "http://127.0.0.1:9000/v1",
            "plane": "local",
        }
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        process_deploy_callback(
            reg1,
            body,
            idempotency_key="restart-1",
            body_bytes=raw,
            signature_header=sign_body(raw, HMAC_KEY),
            hmac_key=HMAC_KEY,
        )
        reg1.close()

        reg2 = SqliteRegistry(db_path)
        got = reg2.get("warming-llama")
        assert got is not None
        assert got.status == ModelStatus.READY
        assert got.endpoint == "http://127.0.0.1:9000/v1"
        reg2.close()


class TestA2MultiConnectionSameTruth:
    def test_two_connections_same_file(self, db_path: str) -> None:
        a = SqliteRegistry(db_path)
        b = SqliteRegistry(db_path)
        a.upsert(_rec("shared-m", status=ModelStatus.PROVISIONING))
        body = {
            "tenant_id": "",
            "model_id": "shared-m",
            "outcome": "success",
            "revision": "r9",
            "endpoint": "http://x/v1",
        }
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        process_deploy_callback(
            a,
            body,
            idempotency_key="multi-1",
            body_bytes=raw,
            signature_header=sign_body(raw, HMAC_KEY),
            hmac_key=HMAC_KEY,
        )
        got = b.get("shared-m")
        assert got is not None
        assert got.status == ModelStatus.READY
        assert got.revision == "r9"
        a.close()
        b.close()


class TestA3Idempotency:
    def test_replay_same_hash(self, sql_reg: SqliteRegistry) -> None:
        body = {
            "tenant_id": "",
            "model_id": "m-idem",
            "outcome": "success",
            "revision": "r1",
            "endpoint": "http://e/v1",
        }
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        sig = sign_body(raw, HMAC_KEY)
        r1 = process_deploy_callback(
            sql_reg,
            body,
            idempotency_key="k-same",
            body_bytes=raw,
            signature_header=sig,
            hmac_key=HMAC_KEY,
        )
        r2 = process_deploy_callback(
            sql_reg,
            body,
            idempotency_key="k-same",
            body_bytes=raw,
            signature_header=sig,
            hmac_key=HMAC_KEY,
        )
        assert r1["idempotent_replay"] is False
        assert r2["idempotent_replay"] is True
        assert r2["status"] == r1["status"]
        assert r2["row_version"] == r1["row_version"]
        # 僅一列 callback
        assert sql_reg.get_callback("k-same") is not None

    def test_conflict_different_body(self, sql_reg: SqliteRegistry) -> None:
        body1 = {
            "tenant_id": "",
            "model_id": "m-conflict",
            "outcome": "success",
            "revision": "r1",
            "endpoint": "http://a",
        }
        body2 = {
            "tenant_id": "",
            "model_id": "m-conflict",
            "outcome": "success",
            "revision": "r2",
            "endpoint": "http://b",
        }
        raw1 = json.dumps(body1, ensure_ascii=False, separators=(",", ":")).encode()
        process_deploy_callback(
            sql_reg,
            body1,
            idempotency_key="k-diff",
            body_bytes=raw1,
            signature_header=sign_body(raw1, HMAC_KEY),
            hmac_key=HMAC_KEY,
        )
        raw2 = json.dumps(body2, ensure_ascii=False, separators=(",", ":")).encode()
        with pytest.raises(CallbackConflict):
            process_deploy_callback(
                sql_reg,
                body2,
                idempotency_key="k-diff",
                body_bytes=raw2,
                signature_header=sign_body(raw2, HMAC_KEY),
                hmac_key=HMAC_KEY,
            )


class TestA4CallbackAdmit:
    def test_failure_then_admit_400(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(_rec("warm", status=ModelStatus.PROVISIONING))
        body = {
            "tenant_id": "",
            "model_id": "warm",
            "outcome": "failure",
            "status": "FAILED",
            "revision": "r1",
            "error_code": "PULL_FAILED",
            "error_detail": "boom",
        }
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        process_deploy_callback(
            sql_reg,
            body,
            idempotency_key="fail-1",
            body_bytes=raw,
            signature_header=sign_body(raw, HMAC_KEY),
            hmac_key=HMAC_KEY,
        )
        svc = ModelGWService(registry=sql_reg)
        with pytest.raises(Exception) as ei:
            svc.admit_or_raise("warm")
        assert getattr(ei.value, "code", None) == CODE_NOT_READY
        assert getattr(ei.value, "http_hint", None) == 400

    def test_success_ready_admit_allow(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(_rec("warm2", status=ModelStatus.PROVISIONING, revision="rx"))
        body = {
            "tenant_id": "",
            "model_id": "warm2",
            "outcome": "success",
            "revision": "rx",
            "endpoint": "http://ok",
            "license": "Apache-2.0",
        }
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        process_deploy_callback(
            sql_reg,
            body,
            idempotency_key="ok-1",
            body_bytes=raw,
            signature_header=sign_body(raw, HMAC_KEY),
            hmac_key=HMAC_KEY,
        )
        result = ModelGWService(registry=sql_reg).admit_or_raise("warm2")
        assert result.allowed


class TestA5TenantSchema:
    def test_pk_tenant_model(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.insert_if_absent(_rec("t-model"), tenant_id="")
        sql_reg.insert_if_absent(_rec("t-model", revision="other"), tenant_id="tenant-a")
        assert sql_reg.get_for_tenant("", "t-model") is not None
        assert sql_reg.get_for_tenant("tenant-a", "t-model") is not None
        # Protocol get 用預設空租戶
        assert sql_reg.get("t-model") is not None
        assert sql_reg.get("t-model").revision == "r1"


class TestA6ZeroCrossWire:
    def test_build_registry_does_not_require_wire(self, monkeypatch, db_path: str) -> None:
        monkeypatch.delenv("MODELGW_WIRE_MODE", raising=False)
        monkeypatch.setenv("MODELGW_REGISTRY_BACKEND", "sql")
        monkeypatch.setenv("MODELGW_DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.setenv("MODELGW_CALLBACK_HMAC_KEY", HMAC_KEY)
        # 不設 TOOL_DUAL_RUN／LINKIN_GUARDRAIL_HMAC_KEY
        monkeypatch.delenv("TOOL_DUAL_RUN", raising=False)
        monkeypatch.delenv("LINKIN_GUARDRAIL_HMAC_KEY", raising=False)
        from backend.modelgw.runtime import wire_mode

        assert wire_mode() == "off"
        reg = build_registry()
        assert isinstance(reg, SqliteRegistry)
        reg.close()


class TestA7ProtocolInMemoryStillWorks:
    def test_inmemory_protocol(self) -> None:
        reg: InMemoryRegistry = InMemoryRegistry([_rec("a")])
        assert reg.get("a") is not None
        assert reg.ready_ids() == ["a"]


class TestA8ReadWriteSeparation:
    def test_admit_does_not_mutate(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(_rec("ro", status=ModelStatus.READY))
        before = sql_reg.row_version("ro")
        ModelGWService(registry=sql_reg).admit_or_raise("ro")
        assert sql_reg.row_version("ro") == before
        # last_used_at 熱寫本波不做
        assert sql_reg.get("ro").last_used_at == 0.0


class TestSeedDoesNotOverwriteCallback:
    def test_seed_skips_existing(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(
            _rec("local-qwen-7b", status=ModelStatus.READY, revision="from-callback")
        )
        n = sql_reg.seed_if_empty(
            [_rec("local-qwen-7b", revision="from-seed"), _rec("new-one")]
        )
        assert n == 1
        assert sql_reg.get("local-qwen-7b").revision == "from-callback"
        assert sql_reg.get("new-one") is not None


class TestHttpCallback:
    @pytest.fixture()
    def client(self, monkeypatch, db_path: str):
        monkeypatch.setenv("MODELGW_CALLBACK_HMAC_KEY", HMAC_KEY)
        monkeypatch.setenv("MODELGW_WIRE_MODE", "off")
        reg = SqliteRegistry(db_path)
        reg.upsert(_rec("warming", status=ModelStatus.PROVISIONING, revision="def456"))
        reset_service(ModelGWService(registry=reg))
        app = FastAPI()
        register_modelgw(app)
        with TestClient(app) as c:
            yield c, reg
        reset_service(None)
        reg.close()

    def test_callback_http_success_and_replay(self, client) -> None:
        c, _reg = client
        body = {
            "tenant_id": "",
            "model_id": "warming",
            "outcome": "success",
            "revision": "def456",
            "endpoint": "http://svc/v1",
            "license": "Apache-2.0",
        }
        headers, raw = _signed_headers(body, idem="http-1")
        # TestClient 需要 content= 才能對齊簽名用的 raw bytes
        resp = c.post(
            "/modelgw/internal/v1/deploy-callback",
            content=raw,
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "READY"
        assert data["idempotent_replay"] is False

        resp2 = c.post(
            "/modelgw/internal/v1/deploy-callback",
            content=raw,
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["idempotent_replay"] is True

        admit = c.post("/modelgw/v1/admit", json={"model_id": "warming"})
        assert admit.status_code == 200

    def test_callback_missing_sig_401(self, client) -> None:
        c, _ = client
        resp = c.post(
            "/modelgw/internal/v1/deploy-callback",
            json={"model_id": "warming", "outcome": "success", "revision": "x"},
            headers={"Idempotency-Key": "nosig"},
        )
        assert resp.status_code == 401

    def test_callback_failure_admit_400(self, client) -> None:
        c, _ = client
        body = {
            "tenant_id": "",
            "model_id": "warming",
            "outcome": "failure",
            "revision": "def456",
        }
        headers, raw = _signed_headers(body, idem="http-fail")
        resp = c.post(
            "/modelgw/internal/v1/deploy-callback",
            content=raw,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "FAILED"
        admit = c.post("/modelgw/v1/admit", json={"model_id": "warming"})
        assert admit.status_code == 400
        assert admit.json()["code"] == CODE_NOT_READY

    def test_provisioning_still_503_before_callback(self, client) -> None:
        c, _ = client
        # 另建一列尚未回調
        # 直接 upsert via service registry
        from backend.modelgw.runtime import get_service

        get_service().registry.upsert(
            _rec("still-warm", status=ModelStatus.PROVISIONING)
        )
        resp = c.post("/modelgw/v1/admit", json={"model_id": "still-warm"})
        assert resp.status_code == 503
        assert resp.json()["code"] == CODE_PROVISIONING
