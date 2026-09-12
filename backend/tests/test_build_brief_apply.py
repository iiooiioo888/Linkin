"""Phase 2：build_brief → MineMCP 落地建築管線測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.build_brief_apply import (
    BuildBriefError,
    apply_build_brief,
    preview_build_brief,
    validate_build_brief,
)
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.narrative_registry import reset_narrative_registry

BUILD_BRIEF = {
    "title": "測試序章廣場",
    "region": "织庭都",
    "location": "0,64,0",
    "style": "织庭盟",
    "prompt": "小型契約廣場，中央立碑。",
    "block_count": 200,
}


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_MCP_AUDIT_PATH", str(tmp_path / "mcp_audit.jsonl"))
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()


@pytest.fixture()
def client(linkin_env):
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def _commit_build_brief(client: TestClient) -> str:
    ws = client.post(
        "/linkin/narrative/workspaces",
        json={"task_id": "task-bb", "snapshot_id": "snap-bb"},
    ).json()["workspace"]["workspace_id"]
    client.put(
        f"/linkin/narrative/workspaces/{ws}/drafts/build_brief",
        json={"value": BUILD_BRIEF},
    )
    commit = client.post(f"/linkin/narrative/workspaces/{ws}/commit")
    assert commit.status_code == 200
    return commit.json()["committed"]["build_brief"]["id"]


def test_validate_build_brief_resolves_faction_style():
    normalized = validate_build_brief(BUILD_BRIEF)
    assert normalized["style"] in {"织梦典章", "白石圣殿", "契约广场", "金线回廊"}
    assert normalized["prompt"] == BUILD_BRIEF["prompt"]


def test_validate_build_brief_missing_prompt():
    with pytest.raises(BuildBriefError) as exc:
        validate_build_brief({"title": "x"})
    assert exc.value.code == "missing_prompt"


def test_validate_build_brief_block_limit():
    with pytest.raises(BuildBriefError) as exc:
        validate_build_brief({**BUILD_BRIEF, "block_count": 99999})
    assert exc.value.code == "block_limit"


def test_preview_build_brief_happy_path(linkin_env):
    preview = preview_build_brief(validate_build_brief(BUILD_BRIEF))
    assert preview["dry_run"] is True
    assert preview["bounds"]["solid_count"] > 0
    assert preview["building"]["id"].startswith("bld-")
    assert preview["preview"]["voxel_count"] > 0


def test_apply_build_brief_happy_path_dry_connector(linkin_env, monkeypatch):
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    brief = validate_build_brief({**BUILD_BRIEF, "id": "bb-test-1"})
    result = apply_build_brief(brief)
    assert result["placement"]["ok"] is True
    assert result["placement"]["blocks_placed"] > 0
    assert result["placement"]["dry_run"] is True
    assert result["brief"]["status"] == "built"
    assert result["building"]["id"].startswith("bld-")


def test_apply_bridge_offline_when_enabled_not_connected(client, linkin_env, monkeypatch):
    brief_id = _commit_build_brief(client)
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "true")
    monkeypatch.setenv("EVOL_MC_MCP_TOKEN", "test-token")

    def _offline_probe():
        return {"connected": False, "ok": False}

    monkeypatch.setattr("backend.tools.minecraft_mcp.probe_connection", _offline_probe)

    resp = client.post(
        "/linkin/build-briefs/apply",
        json={"brief_id": brief_id, "confirm": True},
    )
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["code"] == "bridge_offline"


def test_api_preview_and_apply_flow(client):
    brief_id = _commit_build_brief(client)

    preview = client.post(f"/linkin/build-briefs/{brief_id}/preview", json={})
    assert preview.status_code == 200
    pdata = preview.json()
    assert pdata["bounds"]["solid_count"] > 0
    assert pdata["bridge"]["enabled"] is False

    need_confirm = client.post("/linkin/build-briefs/apply", json={"brief_id": brief_id})
    assert need_confirm.status_code == 400
    assert need_confirm.json()["detail"]["code"] == "confirm_required"

    applied = client.post(
        "/linkin/build-briefs/apply",
        json={"brief_id": brief_id, "confirm": True},
    )
    assert applied.status_code == 200
    adata = applied.json()
    assert adata["placement"]["ok"] is True
    assert adata["brief"]["status"] == "built"
    assert adata["brief"]["building_id"].startswith("bld-")


def test_list_build_briefs(client):
    brief_id = _commit_build_brief(client)
    listed = client.get("/linkin/build-briefs")
    assert listed.status_code == 200
    ids = [b["id"] for b in listed.json()["build_briefs"]]
    assert brief_id in ids
