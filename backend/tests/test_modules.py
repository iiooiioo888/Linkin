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


def test_register_and_list_builtin_modules():
    register_builtin_modules()
    ids = [item.id for item in list_modules()]
    assert ids == ["media-vault", "local-video-studio"]
    assert get_module("minecraft") is None
    studio = get_module("local-video-studio")
    assert studio is not None
    assert studio.api_prefix == "/local-video-studio"
    assert studio.health_snapshot()["ok"] is True


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
    assert [item.id for item in list_modules()] == [
        "media-vault",
        "local-video-studio",
        "demo-world",
    ]


def test_modules_http_catalog(monkeypatch, tmp_path):
    app = FastAPI()
    register_modules(app)
    with TestClient(app) as client:
        listed = client.get("/modules")
        assert listed.status_code == 200
        body = listed.json()
        assert body["count"] == 2
        by_id = {m["id"]: m for m in body["modules"]}
        assert set(by_id) == {"media-vault", "local-video-studio"}
        assert by_id["local-video-studio"]["api_prefix"] == "/local-video-studio"

        missing = client.get("/modules/minecraft")
        assert missing.status_code == 404

        health = client.get("/modules/local-video-studio/health")
        assert health.status_code == 200
        assert health.json()["id"] == "local-video-studio"

        missing_caps = client.get("/modules/nope/capabilities")
        assert missing_caps.status_code == 404


def test_pages_on_catalog_payload():
    register_builtin_modules()
    studio = get_module("local-video-studio")
    assert studio is not None
    payload = studio.to_dict()
    assert payload["gateway_prefix"] == "/modules/local-video-studio/api"


def test_as_header_map_from_asgi_list():
    from backend.modules.gateway import _as_header_map

    raw = [(b"content-type", b"application/json"), (b"content-length", b"12")]
    assert _as_header_map(raw) == {"content-type": "application/json"}
    assert _as_header_map({"X-Trace": "1"}) == {"X-Trace": "1"}
    assert _as_header_map([]) == {}


def test_path_allowed_nested():
    from backend.modules.gateway import path_allowed

    spec = ModuleSpec(
        id="demo",
        title="Demo",
        description="d",
        api_prefix="/demo",
        capabilities=(
            ModuleCapability(
                id="content",
                title="Content",
                description="c",
                api_prefix="/demo",
                routes=("/npcs", "/npcs/{id}/dialogue", "/constitution"),
            ),
        ),
    )
    assert path_allowed(spec, "constitution")
    assert path_allowed(spec, "/npcs/aria/dialogue")
    assert not path_allowed(spec, "grill/start")
    assert not path_allowed(spec, "")
