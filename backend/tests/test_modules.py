"""統一模組目錄：註冊表與 /modules API。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modules import register_builtin_modules, register_modules
from backend.modules.registry import (
    ModuleCapability,
    ModuleSpec,
    get_module,
    list_modules,
    register_module,
    reset_registry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry()
    yield
    reset_registry()


def test_register_and_list_minecraft():
    register_builtin_modules()
    ids = [item.id for item in list_modules()]
    assert ids == ["minecraft"]
    spec = get_module("minecraft")
    assert spec is not None
    assert spec.default_page == "monitor"
    assert spec.api_prefix == "/linkin"
    cap_ids = {cap.id for cap in spec.capabilities}
    assert cap_ids == {"worldview", "content", "admin", "building", "bridge", "monitor", "plugins"}
    pages = {item.key for group in spec.nav_groups for item in group.items}
    assert {"monitor", "world", "admin", "building", "minecraft", "studio", "narrative"} <= pages


def test_reserved_id_rejected():
    with pytest.raises(ValueError, match="核心活動"):
        register_module(ModuleSpec(id="console", title="x", description="y"))


def test_custom_module_appears_in_catalog():
    register_builtin_modules()
    register_module(
        ModuleSpec(
            id="demo-world",
            title="Demo",
            description="範例模組",
            default_page="home",
            capabilities=(
                ModuleCapability(id="ping", title="Ping", description="探活", api_prefix="/demo"),
            ),
        )
    )
    assert [item.id for item in list_modules()] == ["minecraft", "demo-world"]


def test_modules_http_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    from backend.linkin.constitution import reset_cache

    reset_cache()
    app = FastAPI()
    register_modules(app)
    with TestClient(app) as client:
        listed = client.get("/modules")
        assert listed.status_code == 200
        body = listed.json()
        assert body["count"] == 1
        assert body["modules"][0]["id"] == "minecraft"
        assert body["modules"][0]["nav_groups"][0]["items"][0]["key"] == "monitor"

        detail = client.get("/modules/minecraft")
        assert detail.status_code == 200
        assert detail.json()["title"] == "Minecraft"
        admin = next(c for c in detail.json()["capabilities"] if c["id"] == "admin")
        assert "/server/health" in admin["routes"]
        assert "/admin/execute" in admin["routes"]

        missing = client.get("/modules/nope")
        assert missing.status_code == 404

        health = client.get("/modules/minecraft/health")
        assert health.status_code == 200
        snap = health.json()
        assert snap["id"] == "minecraft"
        assert "world" in snap
        assert "bridge" in snap

        pages = client.get("/modules/minecraft/pages")
        assert pages.status_code == 200
        page_body = pages.json()
        assert page_body["id"] == "minecraft"
        assert page_body["default_page"] == "monitor"
        keys = {item["key"] for item in page_body["pages"]}
        assert {"monitor", "world", "admin", "building", "minecraft", "studio", "narrative"} <= keys
        world = next(item for item in page_body["pages"] if item["key"] == "world")
        assert world["capability"] == "worldview"
        assert "/constitution" in world["routes"]

        page = client.get("/modules/minecraft/pages/admin")
        assert page.status_code == 200
        assert page.json()["page"]["capability"] == "admin"
        assert page.json()["page"]["api_prefix"] == "/linkin"

        caps = client.get("/modules/minecraft/capabilities")
        assert caps.status_code == 200
        cap_body = caps.json()
        assert cap_body["id"] == "minecraft"
        assert cap_body["gateway_prefix"] == "/modules/minecraft/api"
        assert {item["id"] for item in cap_body["capabilities"]} == {
            "worldview",
            "content",
            "admin",
            "building",
            "bridge",
            "monitor",
            "plugins",
        }

        missing_page = client.get("/modules/minecraft/pages/nope")
        assert missing_page.status_code == 404
        missing_caps = client.get("/modules/nope/capabilities")
        assert missing_caps.status_code == 404
        reset_cache()


def test_pages_on_catalog_payload():
    register_builtin_modules()
    spec = get_module("minecraft")
    assert spec is not None
    payload = spec.to_dict()
    assert payload["gateway_prefix"] == "/modules/minecraft/api"
    assert payload["page_aliases"]["bridge"] == "minecraft"
    assert payload["page_aliases"]["server"] == "admin"
    assert any(page["key"] == "admin" and page["capability"] == "admin" for page in payload["pages"])
    studio = next(page for page in payload["pages"] if page["key"] == "studio")
    assert studio["roster"] == "agents"


def test_gateway_forwards_allowed_path(monkeypatch, tmp_path):
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    from backend.linkin.api import register_linkin
    from backend.linkin.constitution import reset_cache

    reset_cache()
    app = FastAPI()
    register_linkin(app)
    register_modules(app)
    with TestClient(app) as client:
        via_legacy = client.get("/linkin/constitution")
        via_gateway = client.get("/modules/minecraft/api/constitution")
        assert via_gateway.status_code == 200
        assert via_gateway.json()["world_name"] == via_legacy.json()["world_name"]

        blocked = client.get("/modules/minecraft/api/grill/status")
        assert blocked.status_code == 404

        missing = client.get("/modules/minecraft/api/")
        assert missing.status_code in {404, 405, 307}
        assert via_gateway.headers.get("content-type", "").startswith("application/json")
        reset_cache()


def test_as_header_map_from_asgi_list():
    from backend.modules.gateway import _as_header_map

    raw = [(b"content-type", b"application/json"), (b"content-length", b"12")]
    assert _as_header_map(raw) == {"content-type": "application/json"}
    assert _as_header_map({"X-Trace": "1"}) == {"X-Trace": "1"}
    assert _as_header_map([]) == {}


def test_path_allowed_nested():
    from backend.modules.gateway import path_allowed
    from backend.modules.minecraft import build_minecraft_spec

    spec = build_minecraft_spec()
    assert path_allowed(spec, "constitution")
    assert path_allowed(spec, "/npcs/aria/dialogue")
    assert path_allowed(spec, "server/approvals/sa-1/confirm")
    assert path_allowed(spec, "buildings/bld-1/dispatch")
    assert not path_allowed(spec, "grill/start")
    assert not path_allowed(spec, "")
