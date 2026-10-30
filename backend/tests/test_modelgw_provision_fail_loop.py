"""P3/#132：PROVISIONING 失敗最小閉環（C1–C11 關鍵路徑）。"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock

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
from backend.modelgw.compensate import (
    COMPENSATE_OK,
    COMPENSATE_RETRYABLE,
    LoggingCompensationSink,
    run_compensation,
)
from backend.modelgw.errors import CODE_NOT_READY, CODE_PROVISIONING
from backend.modelgw.provision_controller import (
    EXTRA_COMPENSATE,
    EXTRA_FAIL_REASON,
    EXTRA_STARTED,
    FAIL_REASON_TIMEOUT,
    ensure_provision_started_at,
    provision_timeout_sec,
    tick,
)
from backend.modelgw.registry import ModelRecord, ModelStatus
from backend.modelgw.runtime import reset_service, retry_after_seconds, wire_mode
from backend.modelgw.service import ModelGWService
from backend.modelgw.sql_registry import SqliteRegistry

HMAC_KEY = "test-modelgw-p3-callback-key"


def _rec(model_id: str, status: ModelStatus = ModelStatus.PROVISIONING, **kw: Any) -> ModelRecord:
    extras = dict(kw.pop("extras", {}) or {})
    return ModelRecord(
        model_id=model_id,
        revision=str(kw.get("revision") or "r1"),
        endpoint=str(kw.get("endpoint") or ""),
        lease_id=str(kw.get("lease_id") or ""),
        status=status,
        license="Apache-2.0",
        trust_remote_code=False,
        plane="cloud",
        extras=extras,
    )


def _cb(
    reg: SqliteRegistry,
    body: dict[str, Any],
    *,
    idem: str,
) -> dict[str, Any]:
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    return process_deploy_callback(
        reg,
        body,
        idempotency_key=idem,
        body_bytes=raw,
        signature_header=sign_body(raw, HMAC_KEY),
        hmac_key=HMAC_KEY,
    )


@pytest.fixture()
def sql_reg(tmp_path) -> SqliteRegistry:
    reg = SqliteRegistry(str(tmp_path / "p3.sqlite3"))
    yield reg
    reg.close()


class TestEnvDefaults:
    def test_timeout_default_600(self, monkeypatch) -> None:
        monkeypatch.delenv("MODELGW_PROVISION_TIMEOUT_SEC", raising=False)
        assert provision_timeout_sec() == 600

    def test_timeout_clamp(self, monkeypatch) -> None:
        monkeypatch.setenv("MODELGW_PROVISION_TIMEOUT_SEC", "10")
        assert provision_timeout_sec() == 60
        monkeypatch.setenv("MODELGW_PROVISION_TIMEOUT_SEC", "99999")
        assert provision_timeout_sec() == 3600

    def test_retry_after_default_30(self, monkeypatch) -> None:
        monkeypatch.delenv("MODELGW_RETRY_AFTER", raising=False)
        assert retry_after_seconds() == "30"

    def test_wire_mode_default_off_unchanged(self, monkeypatch) -> None:
        monkeypatch.delenv("MODELGW_WIRE_MODE", raising=False)
        assert wire_mode() == "off"


class TestClock1:
    def test_ensure_first_write(self) -> None:
        ex = ensure_provision_started_at({}, now=1000.0)
        assert ex[EXTRA_STARTED] == 1000.0

    def test_ensure_no_overwrite(self) -> None:
        ex = ensure_provision_started_at({EXTRA_STARTED: 50.0}, now=1000.0)
        assert ex[EXTRA_STARTED] == 50.0

    def test_ensure_force_reset(self) -> None:
        ex = ensure_provision_started_at({EXTRA_STARTED: 50.0}, now=1000.0, force_reset=True)
        assert ex[EXTRA_STARTED] == 1000.0

    def test_backfill_then_timeout(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(_rec("old-warm", extras={}))  # 缺 provision_started_at
        s1 = tick(sql_reg, now=1_000.0, timeout_sec=600)
        assert s1.backfilled == 1
        got = sql_reg.get("old-warm")
        assert got is not None
        assert got.status == ModelStatus.PROVISIONING
        assert got.extras.get(EXTRA_STARTED) == 1_000.0
        assert got.extras.get("clock_backfill") is True
        # 下一輪未超時
        s2 = tick(sql_reg, now=1_100.0, timeout_sec=600)
        assert s2.timed_out == 0
        # 超時
        s3 = tick(sql_reg, now=1_000.0 + 600, timeout_sec=600)
        assert s3.timed_out == 1
        got2 = sql_reg.get("old-warm")
        assert got2 is not None
        assert got2.status == ModelStatus.FAILED
        assert got2.extras.get(EXTRA_FAIL_REASON) == FAIL_REASON_TIMEOUT


class TestTimeoutAndAdmit:
    def test_c1_c2_timeout_failed_admit_400(self, sql_reg: SqliteRegistry, monkeypatch) -> None:
        started = time.time() - 700
        sql_reg.upsert(
            _rec("slow-m", extras={EXTRA_STARTED: started, "lease_id_meta": "x"})
        )
        stats = tick(sql_reg, now=time.time(), timeout_sec=600)
        assert stats.timed_out == 1
        got = sql_reg.get("slow-m")
        assert got is not None
        assert got.status == ModelStatus.FAILED
        assert got.extras[EXTRA_FAIL_REASON] == FAIL_REASON_TIMEOUT

        reset_service(ModelGWService(registry=sql_reg))
        monkeypatch.setenv("MODELGW_WIRE_MODE", "shadow")
        app = FastAPI()
        register_modelgw(app)
        with TestClient(app) as client:
            resp = client.post("/modelgw/v1/admit", json={"model_id": "slow-m"})
            assert resp.status_code == 400
            assert resp.json()["code"] == CODE_NOT_READY
        reset_service(None)

    def test_c11_provisioning_503_retry_after_30(self, sql_reg: SqliteRegistry, monkeypatch) -> None:
        sql_reg.upsert(_rec("warming", extras={EXTRA_STARTED: time.time()}))
        reset_service(ModelGWService(registry=sql_reg))
        monkeypatch.delenv("MODELGW_RETRY_AFTER", raising=False)
        monkeypatch.setenv("MODELGW_WIRE_MODE", "off")
        app = FastAPI()
        register_modelgw(app)
        with TestClient(app) as client:
            resp = client.post("/modelgw/v1/admit", json={"model_id": "warming"})
            assert resp.status_code == 503
            assert resp.json()["code"] == CODE_PROVISIONING
            assert resp.headers.get("Retry-After") == "30"
        reset_service(None)


class TestCompensation:
    def test_c3_c4_compensate_called_no_rollback(self, sql_reg: SqliteRegistry) -> None:
        sink = MagicMock(spec=LoggingCompensationSink)
        sink.delete_isvc.return_value = COMPENSATE_OK
        sink.release_lease.return_value = COMPENSATE_OK
        sink.notify_upstream.return_value = COMPENSATE_OK

        started = 100.0
        sql_reg.upsert(
            _rec("comp-m", lease_id="lease-1", extras={EXTRA_STARTED: started})
        )
        stats = tick(sql_reg, sink=sink, now=100.0 + 600, timeout_sec=600)
        assert stats.timed_out == 1
        assert stats.compensated == 1
        sink.delete_isvc.assert_called()
        sink.release_lease.assert_called()
        sink.notify_upstream.assert_called()
        got = sql_reg.get("comp-m")
        assert got is not None
        assert got.status == ModelStatus.FAILED
        assert got.extras.get(EXTRA_COMPENSATE) == COMPENSATE_OK

    def test_compensate_failure_stays_failed_retryable(self, sql_reg: SqliteRegistry) -> None:
        sink = MagicMock(spec=LoggingCompensationSink)
        sink.delete_isvc.side_effect = RuntimeError("boom")
        sink.release_lease.return_value = COMPENSATE_OK
        sink.notify_upstream.return_value = COMPENSATE_OK
        sql_reg.upsert(_rec("boom-m", extras={EXTRA_STARTED: 1.0}))
        tick(sql_reg, sink=sink, now=1.0 + 600, timeout_sec=600)
        got = sql_reg.get("boom-m")
        assert got is not None
        assert got.status == ModelStatus.FAILED
        assert got.extras.get(EXTRA_COMPENSATE) == COMPENSATE_RETRYABLE
        # 補償-only 重跑
        sink2 = MagicMock(spec=LoggingCompensationSink)
        sink2.delete_isvc.return_value = COMPENSATE_OK
        sink2.release_lease.return_value = COMPENSATE_OK
        sink2.notify_upstream.return_value = COMPENSATE_OK
        s2 = tick(sql_reg, sink=sink2, now=1.0 + 700, timeout_sec=600)
        assert s2.compensated == 1
        assert s2.timed_out == 0
        got2 = sql_reg.get("boom-m")
        assert got2 is not None
        assert got2.status == ModelStatus.FAILED
        assert got2.extras.get(EXTRA_COMPENSATE) == COMPENSATE_OK

    def test_run_compensation_order(self) -> None:
        calls: list[str] = []

        class Ordered:
            def delete_isvc(self, model_id: str, meta: dict) -> str:
                calls.append("delete_isvc")
                return COMPENSATE_OK

            def release_lease(self, lease_id: str | None, model_id: str) -> str:
                calls.append("release_lease")
                return COMPENSATE_OK

            def notify_upstream(self, model_id: str, reason: str) -> str:
                calls.append("notify_upstream")
                return COMPENSATE_OK

        assert run_compensation(Ordered(), model_id="m", lease_id="l", reason="t") == COMPENSATE_OK
        assert calls == ["delete_isvc", "release_lease", "notify_upstream"]


class TestRace1AndRetry1:
    def test_c8_late_success_after_timeout_409(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(
            _rec(
                "race-m",
                status=ModelStatus.FAILED,
                extras={
                    EXTRA_STARTED: 1.0,
                    EXTRA_FAIL_REASON: FAIL_REASON_TIMEOUT,
                    EXTRA_COMPENSATE: COMPENSATE_OK,
                },
            )
        )
        body = {
            "tenant_id": "",
            "model_id": "race-m",
            "outcome": "success",
            "revision": "r9",
            "endpoint": "http://x/v1",
        }
        with pytest.raises(CallbackConflict) as ei:
            _cb(sql_reg, body, idem="late-success-1")
        assert ei.value.code == "STATUS_TRANSITION_DENIED"
        assert ei.value.http_status == 409
        assert sql_reg.get("race-m").status == ModelStatus.FAILED  # type: ignore[union-attr]

    def test_c10_reprovision_from_failed(self, sql_reg: SqliteRegistry) -> None:
        sql_reg.upsert(
            _rec(
                "retry-m",
                status=ModelStatus.FAILED,
                revision="old",
                extras={
                    EXTRA_STARTED: 10.0,
                    EXTRA_FAIL_REASON: FAIL_REASON_TIMEOUT,
                    EXTRA_COMPENSATE: COMPENSATE_OK,
                },
            )
        )
        body = {
            "tenant_id": "",
            "model_id": "retry-m",
            "outcome": "reprovision",
            "revision": "old",
        }
        before = time.time()
        snap = _cb(sql_reg, body, idem="reprov-1")
        assert snap["status"] == "PROVISIONING"
        got = sql_reg.get("retry-m")
        assert got is not None
        assert got.status == ModelStatus.PROVISIONING
        assert EXTRA_FAIL_REASON not in got.extras
        assert EXTRA_COMPENSATE not in got.extras
        assert float(got.extras[EXTRA_STARTED]) >= before

    def test_assert_failed_to_ready_denied(self) -> None:
        with pytest.raises(CallbackConflict) as ei:
            assert_status_transition("FAILED", "READY")
        assert ei.value.code == "STATUS_TRANSITION_DENIED"

    def test_assert_failed_to_provisioning_ok(self) -> None:
        assert_status_transition("FAILED", "PROVISIONING")


class TestCallbackSetsClock:
    def test_provisioning_callback_writes_started_at(self, sql_reg: SqliteRegistry) -> None:
        body = {
            "tenant_id": "",
            "model_id": "new-warm",
            "outcome": "reprovision",  # 新建也可
            "status": "PROVISIONING",
            "revision": "r0",
        }
        # 先塞 FAILED 再 reprovision 較貼近；或直接 create via allow_create with PROVISIONING
        sql_reg.upsert(_rec("new-warm", status=ModelStatus.FAILED, extras={EXTRA_FAIL_REASON: "x"}))
        _cb(sql_reg, body, idem="clock-1")
        got = sql_reg.get("new-warm")
        assert got is not None
        assert EXTRA_STARTED in got.extras
