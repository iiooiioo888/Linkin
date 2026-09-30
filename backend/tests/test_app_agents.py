"""應用層四部門席位：分派、審查閘、本地模板對齊憲法。"""

from __future__ import annotations

import json

import pytest

from backend.linkin.app_agents import (
    AppAgentError,
    dispatch_application_drafts,
    seats_for_keys,
)
from backend.linkin.constitution import allowed_styles_for_region
from backend.linkin.narrative_generate import NarrativeGenerateError, generate_narrative_drafts
from backend.linkin.narrative_starter import fallback_starter_pack
from backend.linkin.tools import (
    validate_builder_generate,
    validate_item_create,
    validate_npc_create,
    validate_quest_generate,
)

STORY = {
    "title": "靈丝残章",
    "summary": "旅人在織庭都追尋失落的織夢記憶。",
    "region": "织庭都",
    "chapters": ["序章"],
    "tags": ["主線"],
}
QUEST = {
    "title": "支線：遺失的織夢殘章",
    "quest_type": "支线",
    "difficulty": "普通",
    "region": "织庭都",
    "description": "向青禾回報殘章下落。",
    "player_id": "traveler-01",
}
NPC = {
    "name": "青禾",
    "faction": "织庭盟",
    "occupation": "典章抄錄者",
    "personality": "沉靜",
    "backstory": "長駐織庭都，記錄旅人口述。",
    "location": "织庭都",
    "speech_style": "白描",
}
ITEM = {
    "name": "靈丝殘章",
    "type": "消耗品",
    "rarity": "common",
    "attributes": {"power": 8},
    "description": "共鳴碎片。",
}
BUILD = {
    "title": "序章廣場",
    "region": "织庭都",
    "location": "0,64,0",
    "style": "契约广场",
    "prompt": "中央立契約碑。",
    "block_count": 400,
    "notes": "僅意圖。",
}


def _fake_llm(prompt: str, system: str = "", trace_label: str = "", **_kwargs: object) -> str:
    assert "應用層執行席" in system
    assert trace_label.startswith("app_agent:")
    assert prompt
    payloads = {
        "app_agent:narrative": {"story_arc": STORY, "quest": QUEST},
        "app_agent:npc": {"npc": NPC},
        "app_agent:item": {"item": ITEM},
        "app_agent:build": {"build_brief": BUILD},
    }
    return json.dumps(payloads[trace_label], ensure_ascii=False)


def test_seats_cover_draft_keys_without_second_chain():
    seats = seats_for_keys(["build_brief", "npc", "story_arc", "quest", "item"])
    assert [seat.department for seat in seats] == ["narrative", "npc", "item", "build"]
    assert seats[0].executor_id == "custom_linkin_narrative_executor"
    assert seats[0].reviewer_id == "custom_linkin_narrative_reviewer"
    assert seats[0].keys == ("story_arc", "quest")


def test_dispatch_one_call_per_department(monkeypatch):
    labels: list[str] = []

    def _spy(prompt: str, system: str = "", trace_label: str = "", **kwargs: object) -> str:
        labels.append(trace_label)
        return _fake_llm(prompt, system=system, trace_label=trace_label, **kwargs)

    monkeypatch.setattr("backend.linkin.app_agents.call_llm", _spy)
    result = dispatch_application_drafts(
        brief="織庭都的殘章",
        keys=["item", "story_arc", "quest", "npc", "build_brief"],
        region="织庭都",
    )
    assert labels == [
        "app_agent:narrative",
        "app_agent:npc",
        "app_agent:item",
        "app_agent:build",
    ]
    assert list(result["drafts"]) == ["item", "story_arc", "quest", "npc", "build_brief"]
    assert [row["school"] for row in result["agents"]] == ["言靈", "共鳴", "賦形", "塑形"]
    assert result["drafts"]["build_brief"]["style"] == "契约广场"


def test_reviewer_rejects_overpowered_item_and_stops(monkeypatch):
    calls = {"n": 0}

    def _spy(prompt: str, system: str = "", trace_label: str = "", **kwargs: object) -> str:
        calls["n"] += 1
        if trace_label == "app_agent:item":
            bad = {**ITEM, "attributes": {"power": 99}}
            return json.dumps({"item": bad}, ensure_ascii=False)
        return _fake_llm(prompt, system=system, trace_label=trace_label, **kwargs)

    monkeypatch.setattr("backend.linkin.app_agents.call_llm", _spy)
    with pytest.raises(AppAgentError) as exc:
        dispatch_application_drafts(brief="失衡道具", keys=["story_arc", "quest", "item"])
    assert exc.value.code == "review_rejected"
    assert calls["n"] == 2


def test_generate_maps_agent_error(monkeypatch):
    monkeypatch.setattr("backend.linkin.narrative_generate._llm_ready", lambda: True)

    def _boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("upstream down")

    monkeypatch.setattr("backend.linkin.app_agents.call_llm", _boom)
    with pytest.raises(NarrativeGenerateError) as exc:
        generate_narrative_drafts(brief="織庭都", keys=["npc"])
    assert exc.value.code == "llm_failed"


def test_fallback_pack_passes_constitution_gates():
    pack = fallback_starter_pack(region="织庭都", theme="靈丝残章")
    allowed = allowed_styles_for_region("织庭都") or []
    assert pack["build_brief"]["style"] in allowed
    validate_quest_generate(pack["quest"])
    validate_npc_create(pack["npc"])
    validate_item_create(pack["item"])
    validate_builder_generate(pack["build_brief"])
