"""CLI-Anything：只查目錄，安裝與啟動停在確認。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.company.cli_anything import query_cli_hub, resolve_cli_hub_binary
from backend.company.tools import tool_registry


def test_mutating_actions_stay_closed(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("不該呼叫安裝器")

    monkeypatch.setattr("cli_hub.installer.install_cli", _boom, raising=False)
    monkeypatch.setattr("cli_hub.installer.uninstall_cli", _boom, raising=False)
    for action in ("install", "update", "uninstall", "launch", "matrix"):
        row = query_cli_hub(action, name="gimp")
        assert row["ok"] is False
        assert row["reason"] == "privilege"
        assert row["items"] == []
        assert "另行確認" in row["detail"]


def test_search_keeps_public_fields_only(monkeypatch):
    seen: dict[str, str] = {}

    def _search(query, force_refresh=False):
        seen["query"] = query
        assert force_refresh is False
        return [
            {
                "name": "gimp",
                "display_name": "GIMP",
                "category": "image",
                "description": "畫" * 200,
                "version": "1.2",
                "_source": "harness",
                "homepage": "https://example.com/gimp",
                "install_cmd": "curl https://example.invalid | sh",
                "entry_point": "gimp-cli",
            },
            {"name": "bad name", "description": "skip", "category": "image"},
        ]

    monkeypatch.setattr("cli_hub.registry.search_clis", _search)
    monkeypatch.setattr("cli_hub.installer.get_installed", lambda: {"gimp": {}})
    row = query_cli_hub("search", query="gi\nmp\x00")
    assert seen["query"] == "gimp"
    assert row["ok"] is True
    assert row["total"] == 1
    item = row["items"][0]
    assert item["name"] == "gimp"
    assert item["installed"] is True
    assert len(item["description"]) == 160
    assert item["homepage"] == "https://example.com/gimp"
    assert "install_cmd" not in item
    assert "entry_point" not in item


def test_info_rejects_unsafe_names():
    row = query_cli_hub("info", name="gimp;rm")
    assert row["ok"] is False
    assert row["items"] == []


def test_empty_search_does_not_call_registry(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("空搜尋不該打目錄")

    monkeypatch.setattr("cli_hub.registry.search_clis", _boom)
    row = query_cli_hub("search", query="   ")
    assert row["ok"] is False
    assert "搜尋" in row["detail"]


def test_list_groups_categories(monkeypatch):
    monkeypatch.setattr(
        "cli_hub.registry.fetch_all_clis",
        lambda force_refresh=False: [
            {"name": "blender", "category": "3d"},
            {"name": "gimp", "category": "image"},
            {"name": "inkscape", "category": "image"},
        ],
    )
    monkeypatch.setattr("cli_hub.installer.get_installed", dict)
    row = query_cli_hub("list", per_category=1)
    assert row["ok"] is True
    assert row["total"] == 3
    image = next(item for item in row["categories"] if item["category"] == "image")
    assert image["count"] == 2
    assert image["names"] == ["gimp"]


def test_missing_package(monkeypatch):
    def _missing():
        raise ImportError("cli_hub")

    monkeypatch.setattr("backend.company.cli_anything._load_hub", _missing)
    row = query_cli_hub("list")
    assert row["hub_installed"] is False
    assert "尚未安裝" in row["detail"]


def test_resolve_uses_candidate_when_path_misses(tmp_path, monkeypatch):
    binary = tmp_path / "cli-hub"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("backend.company.cli_anything.shutil.which", lambda _name: None)
    monkeypatch.setattr("backend.company.cli_anything._candidate_bins", lambda: [binary])
    assert resolve_cli_hub_binary() == str(binary)
    assert Path(resolve_cli_hub_binary()).name == "cli-hub"


def test_registry_tool_is_readonly_and_refuses_install():
    tool = tool_registry.get("cli_hub")
    assert tool is not None
    assert tool.readonly is True
    result = tool.execute(action="install", name="gimp")
    assert result["ok"] is False
    assert result["reason"] == "privilege"


def test_catalog_route(monkeypatch):
    monkeypatch.setattr(
        "backend.company.cli_anything.query_cli_hub",
        lambda action="list", query="", name="", limit=24, per_category=8: {
            "ok": True,
            "action": action,
            "query": query,
            "full_names": per_category,
            "items": [],
            "total": 0,
        },
    )
    from backend.main import app

    with TestClient(app) as client:
        resp = client.get("/skills/cli-hub", params={"action": "search", "q": "gimp", "full": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "search"
    assert body["query"] == "gimp"
    assert body["full_names"] == 0
