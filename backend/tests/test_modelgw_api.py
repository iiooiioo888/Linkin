"""ModelGW FastAPI 掛載：HTTP 映射與 health／admit／chat。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modelgw.api import register_modelgw
from backend.modelgw.errors import CODE_NOT_READY, CODE_PROVISIONING, CODE_UNSUPPORTED
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus
from backend.modelgw.runtime import reset_service
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
def client(monkeypatch):
    reg = InMemoryRegistry(
        [
            _rec("ready-a"),
            _rec("warming", status=ModelStatus.PROVISIONING),
            _rec("dead", status=ModelStatus.FAILED),
        ]
    )
    reset_service(ModelGWService(registry=reg))
    monkeypatch.setenv("MODELGW_WIRE_MODE", "off")
    monkeypatch.setenv("MODELGW_RETRY_AFTER", "17")
    app = FastAPI()
    register_modelgw(app)
    with TestClient(app) as c:
        yield c
    reset_service(None)


class TestModelGWHttp:
    def test_healthz(self, client: TestClient) -> None:
        resp = client.get("/modelgw/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "modelgw"
        assert body["wire_mode"] == "off"
        assert body["registry_size"] == 3
        assert body["ready_count"] == 1

    def test_admit_allow(self, client: TestClient) -> None:
        resp = client.post("/modelgw/v1/admit", json={"model_id": "ready-a"})
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    def test_admit_provisioning_503(self, client: TestClient) -> None:
        resp = client.post("/modelgw/v1/admit", json={"model_id": "warming"})
        assert resp.status_code == 503
        body = resp.json()
        assert body["code"] == CODE_PROVISIONING
        assert resp.headers.get("Retry-After") == "17"
        assert resp.headers.get("content-type", "").startswith("application/problem+json")

    def test_admit_unsupported_400(self, client: TestClient) -> None:
        resp = client.post("/modelgw/v1/admit", json={"model": "no-such-model"})
        assert resp.status_code == 400
        assert resp.json()["code"] == CODE_UNSUPPORTED

    def test_admit_not_ready_400(self, client: TestClient) -> None:
        resp = client.post("/modelgw/v1/admit", json={"model_id": "dead"})
        assert resp.status_code == 400
        assert resp.json()["code"] == CODE_NOT_READY

    def test_chat_completions_mocked(self, client: TestClient, monkeypatch) -> None:
        def fake_llm(prompt, system=None, model=None, **kwargs):
            return f"echo:{model}:{prompt}"

        monkeypatch.setattr("backend.core.llm.call_llm", fake_llm)
        resp = client.post(
            "/modelgw/v1/chat/completions",
            json={
                "model": "ready-a",
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "ready-a"
        assert "echo:ready-a:ping" in body["choices"][0]["message"]["content"]

    def test_chat_provisioning_503(self, client: TestClient) -> None:
        resp = client.post(
            "/modelgw/v1/chat/completions",
            json={
                "model": "warming",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 503
        assert resp.json()["code"] == CODE_PROVISIONING
