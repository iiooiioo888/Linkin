"""靈境 API / 工具鐵律 / RAG 降級測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.evaluation import DimensionResult, EvaluationResult
from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import QualityGateError, get_store, reset_store

NPC_CARD = {
    "name": "司契·白绫",
    "faction": "织庭盟",
    "occupation": "典章司仪",
    "personality": "严谨、温和、把契约视为对世界的承诺",
    "backstory": (
        "白绫自幼在织庭都契约广场抄录织梦者残章。她相信每一座建筑都是记忆的锚点，"
        "也曾在裂隙港目睹即兴改建撕裂金线纹样，从此坚持任何改建必须留下可追溯的契约副本。"
        "她的职责是核对灵丝契约是否与世界观宪法一致，并拒绝空洞的角色卡。"
    ),
    "location": "织庭都",
    "speech_style": "文言夹白",
}


def _pass_eval(_query: str, _answer: str) -> EvaluationResult:
    result = EvaluationResult(source="test")
    for dim in ("accuracy", "completeness", "clarity", "relevance"):
        setattr(result, dim, DimensionResult(9.5, "ok"))
    result.overall = 9.5
    return result


def _fail_eval(_query: str, _answer: str) -> EvaluationResult:
    result = EvaluationResult(source="test")
    for dim in ("accuracy", "completeness", "clarity", "relevance"):
        setattr(result, dim, DimensionResult(3.0, "low"))
    result.overall = 3.0
    return result


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    reset_store()
    reset_constitution_cache()
    yield tmp_path
    reset_store()
    reset_constitution_cache()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def test_constitution_crud(client: TestClient):
    got = client.get("/linkin/constitution")
    assert got.status_code == 200
    body = got.json()
    assert body["world_name"] == "灵境·Linkin"
    assert len(body["factions"]) == 3
    assert body["magic"]["name"] == "灵丝术"
    assert "[待Phase" not in body["magic"]["name"]

    patched = client.put("/linkin/constitution", json={"tagline": "测试更新"})
    assert patched.status_code == 200
    assert patched.json()["tagline"] == "测试更新"
    assert client.get("/linkin/constitution").json()["tagline"] == "测试更新"


def test_npc_crud_and_dialogue(client: TestClient):
    created = client.post("/linkin/npcs", json=NPC_CARD)
    assert created.status_code == 200, created.text
    npc_id = created.json()["npc"]["id"]
    listed = client.get("/linkin/npcs")
    assert listed.json()["count"] == 1

    updated = client.put(f"/linkin/npcs/{npc_id}", json={"occupation": "契约长老"})
    assert updated.status_code == 200
    assert updated.json()["npc"]["occupation"] == "契约长老"

    talk = client.post(
        f"/linkin/npcs/{npc_id}/dialogue",
        json={"playerMessage": "织庭都还欢迎旅人吗？"},
    )
    assert talk.status_code == 200
    body = talk.json()
    assert "reply" in body
    assert "rag" in body

    deleted = client.delete(f"/linkin/npcs/{npc_id}")
    assert deleted.status_code == 200
    assert client.get("/linkin/npcs").json()["count"] == 0


def test_quality_gate_rejects_low_score(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _fail_eval)
    store = get_store()
    with pytest.raises(QualityGateError):
        store.upsert("linkin_npcs", "太短", {"name": "x"}, skip_quality=False)


def test_rag_fallback_json(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    store = get_store()
    status = store.backend_status()
    assert status["chroma"] is False
    assert status["fallback"] == "json"
    stored = store.upsert(
        "linkin_worldview",
        "织庭都是织庭盟的都城，白石圣殿与契约广场构成典章之心。",
        {"kind": "region", "region": "织庭都"},
        record_id="world-loom",
        skip_quality=True,
    )
    assert stored["backend"] == "json"
    hits = store.search("linkin_worldview", "织庭都 契约广场")
    assert hits
    assert hits[0]["backend"] == "json"
    assert hits[0]["similarity"] >= 0.75


def _collect_paths(app) -> set[str]:
    paths: set[str] = set()
    stack: list = list(getattr(app, "routes", []) or [])
    while stack:
        route = stack.pop()
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        nested = getattr(route, "routes", None)
        if nested:
            stack.extend(nested)
        original = getattr(route, "original_router", None)
        if original is not None:
            stack.extend(getattr(original, "routes", []) or [])
    return paths


def test_existing_chat_and_monitor_routes_untouched():
    from backend.main import app

    paths = _collect_paths(app)
    assert "/chat" in paths
    assert "/linkin/overview" in paths
    assert "/linkin/constitution" in paths
    assert "/linkin/npcs" in paths
    assert "/linkin/events" in paths
    assert "/linkin/quests/{quest_id}" in paths or any(p.endswith("/quests/{quest_id}") for p in paths)


def test_entity_delete_and_events(client: TestClient):
    quest = client.post(
        "/linkin/quests/generate",
        json={"playerId": "p1", "questType": "日常", "difficulty": "简单", "region": "宁渊谷"},
    )
    assert quest.status_code == 200
    quest_id = quest.json()["quest"]["id"]
    events = client.get("/linkin/events")
    assert events.status_code == 200
    assert events.json()["count"] >= 1

    deleted = client.delete(f"/linkin/quests/{quest_id}")
    assert deleted.status_code == 200
    assert client.get("/linkin/quests").json()["count"] == 0

    item = client.post(
        "/linkin/items",
        json={"name": "苔石护符", "type": "防具", "rarity": "common", "attributes": {"power": 4}},
    )
    assert item.status_code == 200
    item_id = item.json()["item"]["id"]
    assert client.delete(f"/linkin/items/{item_id}").status_code == 200
    missing = client.delete("/linkin/items/no-such-item")
    assert missing.status_code == 404


def test_seed_linkin_roles(linkin_env):
    from backend.company.role_catalog import get_snapshot
    from backend.linkin.roles import seed_linkin_roles

    roles = seed_linkin_roles()
    assert len(roles) == 16
    director = get_snapshot("custom_linkin_build_director")
    assert director is not None
    assert director["level"] == 1
    assert "place_block" not in (director.get("tools_allowed") or [])
    assert "execute_command" not in (director.get("tools_allowed") or [])
    prompt = director["system_prompt"]
    assert "灵境意志" in prompt or "灵境·Linkin" in prompt
    assert "[待Phase" not in prompt
    assert "织庭盟" in prompt
    assert "灵丝术" in prompt
    narrative = get_snapshot("custom_linkin_narrative_director")
    assert narrative is not None
    assert "Quest.generate" in (narrative.get("tools_allowed") or [])
    executor = get_snapshot("custom_linkin_build_executor")
    assert executor is not None
    assert executor["level"] == 2
    assert "執行者" in executor["name"] or "执行者" in executor["name"] or "建築" in executor["name"]
    assert "place_block" not in (executor.get("tools_allowed") or [])


def test_seed_refreshes_stale_system_prompt(linkin_env):
    from backend.company.role_catalog import create_custom_role, get_snapshot
    from backend.linkin.roles import seed_linkin_roles

    create_custom_role(
        {
            "id": "linkin_build_director",
            "name": "建築總監",
            "level": 1,
            "system_prompt": "旧提示词 [待Phase 1补充] 三大阵营（需在Phase 1中具体定义）",
        }
    )
    stale = get_snapshot("custom_linkin_build_director")
    assert stale is not None
    assert "[待Phase" in stale["system_prompt"]

    seed_linkin_roles()
    refreshed = get_snapshot("custom_linkin_build_director")
    assert refreshed is not None
    assert "[待Phase" not in refreshed["system_prompt"]
    assert "织庭盟" in refreshed["system_prompt"]
    assert "灵丝术" in refreshed["system_prompt"]


def test_seed_linkin_roles_skips_staff_when_director_fails(linkin_env, monkeypatch):
    from backend.company.role_catalog import get_snapshot
    from backend.linkin import roles as roles_mod

    original = roles_mod._safe_create

    def _fail_build_director(payload):
        if payload.get("id") == "linkin_build_director":
            return None
        return original(payload)

    monkeypatch.setattr(roles_mod, "_safe_create", _fail_build_director)
    seeded = roles_mod.seed_linkin_roles()
    assert len(seeded) == 12
    assert get_snapshot("custom_linkin_build_director") is None
    assert get_snapshot("custom_linkin_build_executor") is None
    assert get_snapshot("custom_linkin_build_reviewer") is None
    assert get_snapshot("custom_linkin_build_scribe") is None
    assert get_snapshot("custom_linkin_narrative_director") is not None
    assert get_snapshot("custom_linkin_narrative_executor") is not None


def test_format_npc_text_relationships_consistent():
    from backend.linkin.tools import format_npc_text, npc_relationships

    card = {
        "name": "司契·白绫",
        "faction": "织庭盟",
        "occupation": "典章司仪",
        "personality": "严谨",
        "location": "织庭都",
        "speech_style": "文言夹白",
        "backstory": "抄录织梦者残章",
        "relationships": {"雾衡": "互相尊重"},
    }
    text = format_npc_text(card)
    assert "NPC：司契·白绫" in text
    assert "关系：雾衡:互相尊重" in text

    missing = format_npc_text({**card, "relationships": None})
    assert missing.endswith("关系：")
    listed = format_npc_text({**card, "relationships": ["雾衡"]})
    assert listed.endswith("关系：")
    assert npc_relationships({"relationships": ["雾衡"]}) == {}
    assert npc_relationships({"relationships": {"雾衡": "合作"}}) == {"雾衡": "合作"}


