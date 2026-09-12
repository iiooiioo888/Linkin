"""Phase 3：敘事 NPC／任務／道具 → 世界層落地管線測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.evaluation import DimensionResult, EvaluationResult
from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.linkin.narrative_world_apply import (
    WORLD_STATUS_APPLIED,
    WORLD_STATUS_PARTIAL,
    WORLD_STATUS_PENDING,
    apply_world_intents,
    list_pending_intents,
    preview_world_intents,
)

NPC_DRAFT = {
    "name": "敘事測試·青禾",
    "faction": "织庭盟",
    "occupation": "巡禮者",
    "personality": "沉靜、記性極佳",
    "backstory": "青禾在織庭都記錄旅人口述的片段傳說。",
    "location": "0,64,0",
    "speech_style": "白描敘事",
}

QUEST_DRAFT = {
    "title": "支線：遺失的織夢殘章",
    "quest_type": "支线",
    "difficulty": "普通",
    "region": "织庭都",
    "description": "在織庭都尋找被風吹散的織夢殘章。",
    "player_id": "traveler-01",
    "location": "0,64,0",
}

ITEM_DRAFT = {
    "name": "測試靈丝殘章",
    "type": "消耗品",
    "rarity": "common",
    "attributes": {"power": 10},
    "description": "敘事工作區測試道具。",
    "location": "0,64,0",
}


def _pass_eval(_query: str, _answer: str) -> EvaluationResult:
    result = EvaluationResult(source="test")
    for dim in ("accuracy", "completeness", "clarity", "relevance"):
        setattr(result, dim, DimensionResult(9.5, "ok"))
    result.overall = 9.5
    return result


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
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def _commit_world_intents(client: TestClient) -> dict[str, str]:
    ws = client.post(
        "/linkin/narrative/workspaces",
        json={"task_id": "task-world", "snapshot_id": "snap-world"},
    ).json()["workspace"]["workspace_id"]
    client.put(f"/linkin/narrative/workspaces/{ws}/drafts/npc", json={"value": NPC_DRAFT})
    client.put(f"/linkin/narrative/workspaces/{ws}/drafts/quest", json={"value": QUEST_DRAFT})
    client.put(f"/linkin/narrative/workspaces/{ws}/drafts/item", json={"value": ITEM_DRAFT})
    commit = client.post(f"/linkin/narrative/workspaces/{ws}/commit")
    assert commit.status_code == 200, commit.text
    committed = commit.json()["committed"]
    assert committed["npc"]["world_status"] == WORLD_STATUS_PENDING
    assert committed["quest"]["world_status"] == WORLD_STATUS_PENDING
    assert committed["item"]["world_status"] == WORLD_STATUS_PENDING
    return {
        "npc_id": committed["npc"]["id"],
        "quest_id": committed["quest"]["id"],
        "item_id": committed["item"]["id"],
    }


def test_list_pending_after_commit(client: TestClient):
    ids = _commit_world_intents(client)
    pending = client.get("/linkin/world-intents")
    assert pending.status_code == 200
    body = pending.json()["pending"]
    assert body["count"] == 3
    assert ids["npc_id"] in [n["id"] for n in body["npcs"]]
    assert ids["quest_id"] in [q["id"] for q in body["quests"]]
    assert ids["item_id"] in [i["id"] for i in body["items"]]


def test_preview_world_intents(client: TestClient):
    ids = _commit_world_intents(client)
    preview = client.post("/linkin/world-intents/preview", json={"apply_all": True})
    assert preview.status_code == 200
    data = preview.json()
    assert data["count"] == 3
    assert data["dry_run"] is True
    kinds = {row["kind"] for row in data["intents"]}
    assert kinds == {"npc", "quest", "item"}
    npc_preview = next(row for row in data["intents"] if row["kind"] == "npc")
    assert npc_preview["id"] == ids["npc_id"]
    assert npc_preview["spawn"]["x"] == 0


def test_apply_requires_confirm(client: TestClient):
    _commit_world_intents(client)
    need_confirm = client.post("/linkin/world-intents/apply", json={"apply_all": True})
    assert need_confirm.status_code == 400
    assert need_confirm.json()["detail"]["code"] == "confirm_required"


def test_apply_offline_partial_status(client: TestClient, linkin_env):
    ids = _commit_world_intents(client)
    applied = client.post(
        "/linkin/world-intents/apply",
        json={"apply_all": True, "confirm": True},
    )
    assert applied.status_code == 200
    data = applied.json()
    assert data["summary"]["overall_status"] == "partial"
    assert data["summary"]["partial"] == 3
    assert data["bridge"]["spawn_mode"] in {"store_only", "dry_run"}

    quests = client.get("/linkin/quests").json()["quests"]
    quest = next(q for q in quests if q["id"] == ids["quest_id"])
    assert quest["world_status"] == WORLD_STATUS_PARTIAL


def test_apply_idempotent_skip(client: TestClient):
    from backend.linkin.knowledge import COL_NPCS, get_store, upsert_entity
    from backend.linkin.narrative_world_apply import _persist_npc

    ids = _commit_world_intents(client)
    first = apply_world_intents(apply_all=True)
    assert first["summary"]["partial"] == 3

    quest_row = next(row for row in first["results"] if row["kind"] == "quest")
    upsert_entity("quests", {**quest_row["store"]["entity"], "world_status": WORLD_STATUS_APPLIED})

    npc = get_store().get(COL_NPCS, ids["npc_id"])
    assert npc is not None
    from backend.linkin.narrative_world_apply import _npc_from_record

    _persist_npc(_npc_from_record(npc), {"world_status": WORLD_STATUS_APPLIED})

    item_row = next(row for row in first["results"] if row["kind"] == "item")
    upsert_entity("items", {**item_row["store"]["entity"], "world_status": WORLD_STATUS_APPLIED})

    pending = list_pending_intents()
    assert pending["count"] == 0

    second = apply_world_intents(npc_ids=[ids["npc_id"]], quest_ids=[ids["quest_id"]], item_ids=[ids["item_id"]])
    assert second["summary"]["skipped"] == 3


def test_apply_bridge_enabled_offline_returns_partial_not_409(client: TestClient, monkeypatch):
    _commit_world_intents(client)
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "true")
    monkeypatch.setenv("EVOL_MC_MCP_TOKEN", "test-token")

    def _offline_probe():
        return {"connected": False, "ok": False}

    monkeypatch.setattr("backend.tools.minecraft_mcp.probe_connection", _offline_probe)

    applied = client.post(
        "/linkin/world-intents/apply",
        json={"apply_all": True, "confirm": True},
    )
    assert applied.status_code == 200
    data = applied.json()
    assert data["bridge"].get("bridge_offline") is True
    assert data["summary"]["overall_status"] == "partial"


def test_preview_module_function(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as client:
        ids = _commit_world_intents(client)
    preview = preview_world_intents(npc_ids=[ids["npc_id"]])
    assert preview["count"] == 1
    assert preview["intents"][0]["kind"] == "npc"


def test_list_pending_module(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as client:
        _commit_world_intents(client)
    pending = list_pending_intents()
    assert pending["count"] == 3
