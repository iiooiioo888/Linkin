"""插件目錄／dsh-context 可視化適配 API 測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modules import plugins_api
from backend.modules.plugin_manager import (
    DSH_CONTEXT_PIN,
    DSH_CONTEXT_PLUGIN_ID,
    DSH_CONTEXT_REPO,
    reset_plugin_manager,
)


@pytest.fixture(autouse=True)
def _reset_plugins():
    reset_plugin_manager()
    yield
    reset_plugin_manager()


def _client() -> TestClient:
    app = FastAPI()
    plugins_api.register_plugin_routes(app)
    return TestClient(app)


def test_plugins_catalog_lists_dsh_context():
    client = _client()
    resp = client.get("/plugins/catalog")
    assert resp.status_code == 200
    catalog = resp.json()["catalog"]
    ids = {row["plugin_id"] for row in catalog}
    assert DSH_CONTEXT_PLUGIN_ID in ids
    row = next(r for r in catalog if r["plugin_id"] == DSH_CONTEXT_PLUGIN_ID)
    assert row["repo"] == DSH_CONTEXT_REPO
    assert row["default_pin"] == DSH_CONTEXT_PIN
    assert row["remote_fetch"] is False
    assert "/context" in row["commands"]
    assert row["status"] == "available"


def test_dsh_context_explicit_install_and_toggle():
    client = _client()
    bad = client.post(f"/plugins/{DSH_CONTEXT_PLUGIN_ID}/toggle", json={"enabled": False})
    assert bad.status_code == 404

    inst = client.post(f"/plugins/{DSH_CONTEXT_PLUGIN_ID}/install")
    assert inst.status_code == 200
    assert inst.json()["ok"] is True

    on = client.post(f"/plugins/{DSH_CONTEXT_PLUGIN_ID}/toggle", json={"enabled": True})
    assert on.status_code == 200
    assert on.json()["enabled"] is True
    assert on.json()["context_surfaces"] is True

    catalog = client.get("/plugins").json()["catalog"]
    row = next(r for r in catalog if r["plugin_id"] == DSH_CONTEXT_PLUGIN_ID)
    assert row["enabled"] is True
    assert row["status"] == "enabled"

    off = client.post(f"/plugins/{DSH_CONTEXT_PLUGIN_ID}/toggle", json={"enabled": False})
    assert off.status_code == 200
    assert off.json()["enabled"] is False


def test_toggle_installs_from_catalog_when_missing():
    """啟用未安裝目錄項：仍屬顯式 API，允許一併安裝。"""
    client = _client()
    out = client.post(f"/plugins/{DSH_CONTEXT_PLUGIN_ID}/toggle", json={"enabled": True})
    assert out.status_code == 200
    assert out.json()["ok"] is True
    assert out.json()["enabled"] is True


def test_contract_whitelist_includes_dsh_context_repo():
    from backend.modules.plugin_manager import PluginManager

    mgr = PluginManager()
    assert DSH_CONTEXT_REPO in mgr.policy.whitelisted_repos
    ok = mgr.install(DSH_CONTEXT_PLUGIN_ID, DSH_CONTEXT_REPO, version=DSH_CONTEXT_PIN)
    assert ok["ok"] is True
    # 未白名單仍拒絕
    deny = mgr.install("evil", "evil/not-listed", version="1.0.0")
    assert deny["ok"] is False
