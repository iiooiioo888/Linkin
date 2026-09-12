"""Minecraft 第三方插件目錄、設定與 URL 探測測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.minecraft_plugins import (
    PLUGIN_CATALOG,
    PluginUrlError,
    list_catalog,
    public_settings,
    reset_settings_cache,
    update_settings,
    validate_map_url,
)


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    reset_store()
    reset_constitution_cache()
    reset_settings_cache()
    yield tmp_path
    reset_settings_cache()
    reset_store()
    reset_constitution_cache()


@pytest.fixture()
def client(linkin_env):
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def test_catalog_shape():
    items = list_catalog()
    assert len(items) == len(PLUGIN_CATALOG)
    ids = {item["id"] for item in items}
    assert "dynmap" in ids
    assert "bluemap" in ids
    assert "squaremap" in ids
    for item in items:
        assert "name" in item
        assert "purpose" in item
        assert "status" in item
        assert "config_fields" in item


def test_settings_crud_roundtrip(client: TestClient):
    empty = client.get("/linkin/minecraft/plugins/settings")
    assert empty.status_code == 200
    assert empty.json()["map_url"] is None

    saved = client.put(
        "/linkin/minecraft/plugins/settings",
        json={
            "active_map_plugin": "dynmap",
            "plugins": {
                "dynmap": {
                    "enabled": True,
                    "map_url": "https://example.com/",
                    "api_port": 8123,
                }
            },
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["active_map_plugin"] == "dynmap"
    assert body["map_url"] == "https://example.com/"
    assert body["plugins"]["dynmap"]["enabled"] is True
    assert body["plugins"]["dynmap"]["api_port"] == 8123

    catalog = client.get("/linkin/minecraft/plugins/catalog").json()
    dynmap = next(p for p in catalog["plugins"] if p["id"] == "dynmap")
    assert dynmap["enabled"] is True
    assert dynmap["map_url"] == "https://example.com/"
    assert dynmap["active_map"] is True
    assert dynmap["status"] in {"configured", "reachable", "unreachable"}


def test_validate_map_url_blocks_private_and_metadata():
    with pytest.raises(PluginUrlError) as exc:
        validate_map_url("http://127.0.0.1:8123/")
    assert exc.value.code == "blocked_ip"

    with pytest.raises(PluginUrlError):
        validate_map_url("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(PluginUrlError):
        validate_map_url("ftp://map.example.com/")

    with pytest.raises(PluginUrlError):
        validate_map_url("http://localhost:8123/")


def test_update_settings_rejects_unknown_plugin():
    with pytest.raises(PluginUrlError):
        update_settings({"plugins": {"not-a-plugin": {"enabled": True}}})


def test_probe_requires_configured_url(client: TestClient):
    resp = client.post("/linkin/minecraft/plugins/dynmap/probe")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unconfigured"


def test_probe_success(monkeypatch, client: TestClient):
    client.put(
        "/linkin/minecraft/plugins/settings",
        json={
            "plugins": {
                "dynmap": {"enabled": True, "map_url": "https://example.com/"},
            }
        },
    )

    def fake_probe(url: str) -> dict:
        return {
            "checked_at": "2026-01-01T00:00:00+00:00",
            "url": url,
            "ok": True,
            "status": "reachable",
            "status_code": 200,
            "method": "HEAD",
            "error": None,
            "embeddable_hint": "ok",
        }

    monkeypatch.setattr("backend.linkin.minecraft_plugins._http_probe", fake_probe)
    resp = client.post("/linkin/minecraft/plugins/dynmap/probe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["probe"]["ok"] is True
    assert body["connection_status"] == "reachable"

    settings = public_settings()
    assert settings["plugins"]["dynmap"]["last_probe"]["ok"] is True


def test_minecraft_status_includes_plugins_summary(client: TestClient):
    client.put(
        "/linkin/minecraft/plugins/settings",
        json={
            "plugins": {
                "bluemap": {"enabled": True, "map_url": "https://example.com/bluemap"},
            }
        },
    )
    status = client.get("/linkin/minecraft/status").json()
    assert "plugins" in status
    assert status["plugins"]["map_url"] == "https://example.com/bluemap"
