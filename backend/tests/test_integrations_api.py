"""整合層 HTTP API 測試（目錄／啟停／動作閘門）。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.integrations import api as integ_api
from backend.integrations.base import IntegrationConfig
from backend.integrations.memos import MemosClient
from backend.integrations.openpencil import OpenPencilClient
from backend.integrations.openviking import OpenVikingClient
from backend.integrations.ouroboros import OuroborosClient
from backend.integrations.weknora import WeKnoraClient
from backend.integrations.yao import YaoClient


def _cfg(name: str, *, enabled: bool = False) -> IntegrationConfig:
    return IntegrationConfig(name=name, base_url=f"http://stub/{name}", enabled=enabled)


def _transport_ok(*_a, **_k):
    return 200, b'{"ok":true,"data":[]}'


def _build_app() -> TestClient:
    integ_api.reset_registry()
    transport = _transport_ok
    integ_api._REGISTRY = {  # noqa: SLF001 — 測試注入
        "memos": MemosClient(config=_cfg("memos"), transport=transport),
        "openviking": OpenVikingClient(config=_cfg("openviking"), transport=transport),
        "weknora": WeKnoraClient(config=_cfg("weknora"), transport=transport),
        "yao": YaoClient(config=_cfg("yao"), transport=transport),
        "ouroboros": OuroborosClient(config=_cfg("ouroboros"), transport=transport),
        "openpencil": OpenPencilClient(config=_cfg("openpencil"), transport=transport),
    }
    app = FastAPI()
    integ_api.register_integrations(app)
    return TestClient(app)


def test_catalog_lists_six_integrations():
    client = _build_app()
    r = client.get("/integrations/catalog")
    assert r.status_code == 200
    names = [x["name"] for x in r.json()["catalog"]]
    assert names == ["memos", "openviking", "weknora", "yao", "ouroboros", "openpencil"]


def test_list_integrations_default_disabled():
    client = _build_app()
    r = client.get("/integrations")
    assert r.status_code == 200
    items = r.json()["integrations"]
    assert len(items) == 6
    assert all(not i["enabled"] for i in items)


def test_toggle_is_explicit_and_enables_client():
    client = _build_app()
    r = client.post("/integrations/memos/toggle", json={"enabled": True})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "name": "memos", "enabled": True}
    listed = client.get("/integrations").json()["integrations"]
    memos = next(i for i in listed if i["name"] == "memos")
    assert memos["enabled"] is True


def test_yao_action_fails_closed_when_disabled():
    client = _build_app()
    r = client.get("/integrations/yao/workspaces")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error_code"] == "ERR_INTEGRATION_DISABLED"


def test_ouroboros_auto_local_gate_without_enable():
    client = _build_app()
    r = client.post(
        "/integrations/ouroboros/auto",
        json={"goal": "x", "ambiguity": 0.5, "force": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error_code"] == "ERR_INTEGRATION_DISABLED"


def test_openpencil_generate_requires_enable():
    client = _build_app()
    r = client.post("/integrations/openpencil/generate", json={"prompt": "landing"})
    assert r.status_code == 200
    assert r.json()["error_code"] == "ERR_INTEGRATION_DISABLED"


def test_yao_list_after_enable_uses_transport():
    client = _build_app()
    client.post("/integrations/yao/toggle", json={"enabled": True})
    r = client.get("/integrations/yao/workspaces")
    assert r.status_code == 200
    assert r.json()["ok"] is True
