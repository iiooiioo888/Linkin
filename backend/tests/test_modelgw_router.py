"""ModelGW 路由／熔斷／探針：MGW-R4／R5／R6。"""

from __future__ import annotations

import time
from pathlib import Path

from backend.modelgw.circuit import CircuitBreaker, CircuitRegistry
from backend.modelgw.probe import FAIL_PENALTY_MS, probe_once
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus, load_json_seed
from backend.modelgw.service import ModelGWService


def _rec(model_id: str, plane: str = "cloud", **kw) -> ModelRecord:
    base = {
        "model_id": model_id,
        "revision": "r1",
        "status": ModelStatus.READY,
        "license": "Apache-2.0",
        "trust_remote_code": False,
        "plane": plane,
    }
    base.update(kw)
    return ModelRecord(**base)


def test_mgw_r4_ready_closed_invokes() -> None:
    reg = InMemoryRegistry([_rec("alpha"), _rec("beta")])
    svc = ModelGWService(registry=reg)
    calls: list[str] = []

    def llm(*, prompt, model, **kwargs):
        calls.append(model)
        return f"ok:{model}"

    out = svc.invoke_chat("alpha", [{"role": "user", "content": "hi"}], llm)
    assert out.model_id == "alpha"
    assert out.text == "ok:alpha"
    assert out.failover_hops == 0
    assert calls == ["alpha"]


def test_mgw_r5_primary_open_failover() -> None:
    reg = InMemoryRegistry([_rec("primary"), _rec("backup")])
    circuits = CircuitRegistry()
    # 強制主模型 OPEN
    cb = circuits.get("primary")
    cb.state = "OPEN"
    cb.opened_at = time.monotonic()

    svc = ModelGWService(registry=reg, circuits=circuits)
    calls: list[str] = []

    def llm(*, prompt, model, **kwargs):
        calls.append(model)
        return f"ok:{model}"

    out = svc.invoke_chat("primary", [{"role": "user", "content": "hi"}], llm, extras=["backup"])
    assert out.model_id == "backup"
    assert "primary" in out.skipped_open
    assert calls == ["backup"]
    assert out.failover_hops >= 0


def test_mgw_r6_probe_failure_penalty() -> None:
    reg = InMemoryRegistry([_rec("alpha")])
    metrics: dict = {}

    def bad_llm(**kwargs):
        raise RuntimeError("down")

    probe_once(reg, metrics, llm=bad_llm)
    assert metrics["alpha"]["latency_ewma_ms"] == FAIL_PENALTY_MS
    assert metrics["alpha"]["consecutive_fail"] == 1


def test_probe_only_ready_ids() -> None:
    reg = InMemoryRegistry(
        [
            _rec("ready-one"),
            _rec("warming", status=ModelStatus.PROVISIONING),
        ]
    )
    metrics: dict = {}
    seen: list[str] = []

    def llm(*, model, **kwargs):
        seen.append(model)
        return "pong"

    probe_once(reg, metrics, llm=llm)
    assert seen == ["ready-one"]
    assert "warming" not in metrics


def test_json_seed_loader() -> None:
    path = Path(__file__).resolve().parents[1] / "modelgw" / "seeds" / "demo_registry.json"
    rows = load_json_seed(path)
    reg = InMemoryRegistry(rows)
    assert "local-qwen-7b" in reg.ready_ids()
    assert reg.get("warming-llama").status == ModelStatus.PROVISIONING


def test_circuit_trips_on_fail_ratio() -> None:
    cb = CircuitBreaker()
    now = time.monotonic()
    for _ in range(CircuitBreaker.minimum_number_of_calls):
        cb.record(failed=True, now=now)
    assert cb.state == "OPEN"
    assert cb.is_open(now)
