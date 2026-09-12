"""敘事工作區 API：begin → draft → commit 與快照衝突路徑。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.evaluation import DimensionResult, EvaluationResult
from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.linkin.narrative_workspace import ERR_SNAPSHOT_UNRESOLVED

NPC_DRAFT = {
    "name": "敘事測試·青禾",
    "faction": "织庭盟",
    "occupation": "巡禮者",
    "personality": "沉靜、記性極佳、以故事串連記憶",
    "backstory": (
        "青禾在織庭都長大，專門記錄旅人口述的片段傳說。"
        "她相信每一段未完成的對話都會在未來的任務中開花。"
    ),
    "location": "织庭都",
    "speech_style": "白描敘事",
}

QUEST_DRAFT = {
    "title": "支線：遺失的織夢殘章",
    "quest_type": "支线",
    "difficulty": "普通",
    "region": "织庭都",
    "description": "在織庭都尋找被風吹散的織夢殘章，並向青禾回報。",
    "player_id": "traveler-01",
}

ITEM_DRAFT = {
    "name": "測試靈丝殘章",
    "type": "消耗品",
    "rarity": "common",
    "attributes": {"power": 10},
    "description": "敘事工作區測試道具。",
}

BUILD_BRIEF_DRAFT = {
    "title": "測試序章廣場",
    "region": "织庭都",
    "location": "0,64,0",
    "style": "织庭盟",
    "prompt": "小型契約廣場，中央立碑。",
    "block_count": 500,
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


def _begin(client: TestClient, task_id: str = "task-narrative-1", snapshot_id: str = "snap-a") -> str:
    resp = client.post(
        "/linkin/narrative/workspaces",
        json={"task_id": task_id, "snapshot_id": snapshot_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert set(body["known_draft_keys"]) >= {"story_arc", "quest", "npc", "item", "build_brief"}
    return body["workspace"]["workspace_id"]


def test_narrative_begin_write_commit(client: TestClient):
    ws_id = _begin(client)
    put = client.put(
        f"/linkin/narrative/workspaces/{ws_id}/drafts/quest",
        json={"value": QUEST_DRAFT},
    )
    assert put.status_code == 200
    assert "quest" in put.json()["workspace"]["draft_keys"]

    npc = client.post(
        f"/linkin/narrative/workspaces/{ws_id}/draft",
        json={"key": "npc", "value": NPC_DRAFT},
    )
    assert npc.status_code == 200

    commit = client.post(f"/linkin/narrative/workspaces/{ws_id}/commit")
    assert commit.status_code == 200, commit.text
    payload = commit.json()
    assert payload["ok"] is True
    assert payload["workspace"]["state"] == "committed"
    assert "quest" in payload["committed"]
    assert "npc" in payload["committed"]
    assert payload["committed"]["quest"]["world_status"] == "pending_world"
    assert payload["committed"]["npc"]["world_status"] == "pending_world"

    quests = client.get("/linkin/quests").json()["quests"]
    assert any(q["title"] == QUEST_DRAFT["title"] for q in quests)
    npcs = client.get("/linkin/npcs").json()["npcs"]
    assert any(n["name"] == NPC_DRAFT["name"] for n in npcs)


def test_narrative_full_rpg_draft_keys_commit(client: TestClient):
    ws_id = _begin(client)
    client.put(
        f"/linkin/narrative/workspaces/{ws_id}/drafts/story_arc",
        json={
            "value": {
                "title": "靈丝殘章",
                "summary": "旅人在織庭都追尋失落的織夢記憶。",
                "region": "织庭都",
                "chapters": ["序章"],
            }
        },
    )
    client.put(f"/linkin/narrative/workspaces/{ws_id}/drafts/item", json={"value": ITEM_DRAFT})
    client.put(f"/linkin/narrative/workspaces/{ws_id}/drafts/build_brief", json={"value": BUILD_BRIEF_DRAFT})

    commit = client.post(f"/linkin/narrative/workspaces/{ws_id}/commit")
    assert commit.status_code == 200, commit.text
    committed = commit.json()["committed"]
    assert committed["item"]["name"] == ITEM_DRAFT["name"]
    assert committed["item"]["world_status"] == "pending_world"
    assert committed["build_brief"]["status"] == "pending_builder"

    items = client.get("/linkin/items").json()["items"]
    assert any(i["name"] == ITEM_DRAFT["name"] for i in items)


def test_narrative_starter_pack_without_auto_commit(client: TestClient):
    ws_id = _begin(client)
    seeded = client.post(
        f"/linkin/narrative/workspaces/{ws_id}/starter-pack",
        json={"region": "织庭都", "theme": "測試主題"},
    )
    assert seeded.status_code == 200, seeded.text
    body = seeded.json()
    assert body["ok"] is True
    assert body["source"] in {"fallback", "llm"}
    assert set(body["draft_keys"]) >= {"story_arc", "quest", "npc", "item", "build_brief"}
    assert body["workspace"]["state"] == "active"

    quests_before = client.get("/linkin/quests").json()["count"]
    commit = client.post(f"/linkin/narrative/workspaces/{ws_id}/commit")
    assert commit.status_code == 200
    assert client.get("/linkin/quests").json()["count"] >= quests_before + 1


def test_narrative_snapshot_conflict_requires_confirm(client: TestClient):
    ws_id = _begin(client)
    client.put(
        f"/linkin/narrative/workspaces/{ws_id}/drafts/story_arc",
        json={
            "value": {
                "title": "設定片段",
                "summary": "織庭都夜裡會聽見金線共鳴。",
                "region": "织庭都",
            }
        },
    )

    refresh = client.post(
        "/linkin/narrative/workspaces/refresh-l0",
        json={"new_snapshot_id": "snap-b"},
    )
    assert refresh.status_code == 200
    assert ws_id in refresh.json()["affected_workspace_ids"]

    blocked = client.post(f"/linkin/narrative/workspaces/{ws_id}/commit")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error_code"] == ERR_SNAPSHOT_UNRESOLVED

    confirm = client.post(
        f"/linkin/narrative/workspaces/{ws_id}/confirm",
        json={"choice": "rebind", "new_snapshot_id": "snap-b"},
    )
    assert confirm.status_code == 200
    assert confirm.json()["workspace"]["state"] == "active"
    assert confirm.json()["workspace"]["snapshot_id"] == "snap-b"

    commit = client.post(f"/linkin/narrative/workspaces/{ws_id}/commit")
    assert commit.status_code == 200
    assert commit.json()["committed"]["story_arc"]["title"] == "設定片段"


VALID_GENERATE_PAYLOAD = {
    "story_arc": {
        "title": "靈丝残章",
        "summary": "旅人在織庭都追尋失落的織夢記憶。",
        "region": "织庭都",
        "chapters": ["序章", "第一章"],
        "tags": ["主線"],
    },
    "quest": QUEST_DRAFT,
    "npc": NPC_DRAFT,
    "item": ITEM_DRAFT,
    "build_brief": BUILD_BRIEF_DRAFT,
}


def test_narrative_generate_happy_path(client: TestClient, monkeypatch):
    ws_id = _begin(client)

    def _fake_generate(**_kwargs):
        return {"drafts": VALID_GENERATE_PAYLOAD, "source": "llm", "keys": sorted(VALID_GENERATE_PAYLOAD)}

    monkeypatch.setattr("backend.linkin.narrative_api.generate_narrative_drafts", _fake_generate)

    resp = client.post(
        f"/linkin/narrative/workspaces/{ws_id}/generate",
        json={"brief": "織庭都靈丝契約傳說", "locale": "zh-Hant", "region": "织庭都"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "llm"
    assert set(body["replaced_keys"]) == set(VALID_GENERATE_PAYLOAD.keys())
    assert set(body["draft_keys"]) >= set(VALID_GENERATE_PAYLOAD.keys())
    assert body["workspace"]["state"] == "active"
    assert body["workspace"]["drafts"]["story_arc"]["title"] == "靈丝残章"

    quests_before = client.get("/linkin/quests").json()["count"]
    assert quests_before == client.get("/linkin/quests").json()["count"]


def test_narrative_generate_bad_json_keeps_prior_drafts(client: TestClient, monkeypatch):
    ws_id = _begin(client)
    client.put(
        f"/linkin/narrative/workspaces/{ws_id}/drafts/quest",
        json={"value": QUEST_DRAFT},
    )

    def _fail_generate(**_kwargs):
        from backend.linkin.narrative_generate import NarrativeGenerateError

        raise NarrativeGenerateError("LLM 回傳無法解析為 JSON", code="parse_failed", detail="not json")

    monkeypatch.setattr("backend.linkin.narrative_api.generate_narrative_drafts", _fail_generate)

    resp = client.post(
        f"/linkin/narrative/workspaces/{ws_id}/generate",
        json={"brief": "測試 brief"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "parse_failed"
    assert "quest" in detail["workspace"]["draft_keys"]
    assert detail["workspace"]["drafts"]["quest"]["title"] == QUEST_DRAFT["title"]


def test_narrative_generate_unknown_workspace(client: TestClient):
    resp = client.post(
        "/linkin/narrative/workspaces/ws-does-not-exist/generate",
        json={"brief": "測試"},
    )
    assert resp.status_code == 404


def test_narrative_generate_requires_brief(client: TestClient):
    ws_id = _begin(client)
    resp = client.post(f"/linkin/narrative/workspaces/{ws_id}/generate", json={})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "missing_brief"


def test_narrative_list_by_task(client: TestClient):
    ws_id = _begin(client, task_id="task-list-me")
    listed = client.get("/linkin/narrative/workspaces", params={"task_id": "task-list-me"})
    assert listed.status_code == 200
    rows = listed.json()["workspaces"]
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == ws_id

    detail = client.get(f"/linkin/narrative/workspaces/{ws_id}")
    assert detail.status_code == 200
    assert detail.json()["workspace"]["drafts"] == {}
