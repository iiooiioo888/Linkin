"""任務經理上下文包：目錄可查，送給模型的只有相關候選。"""

from __future__ import annotations

import json

import pytest

from backend.company.manager_briefing import (
    TOP_ROLES,
    assemble_manager_context,
    query_role_cards,
    select_relevant,
)
from backend.company.prompts import MANAGER_DECOMPOSE
from backend.company.roles import BUILTIN_TEMPLATES


def _budget():
    from backend.company.budget import BudgetManager

    return BudgetManager(BUILTIN_TEMPLATES["quick_task"].budget)


def test_select_relevant_keeps_overlap_and_counts_omitted():
    cards = [
        {"id": "ui_designer", "search": "登入頁面 視覺", "line": "ui"},
        {"id": "plc_engineer", "search": "plc 連鎖", "line": "plc"},
    ]
    chosen, omitted = select_relevant("請做登入頁面", cards, limit=1)
    assert [card["id"] for card in chosen] == ["ui_designer"]
    assert omitted == 1
    assert chosen[0]["low_relevance"] is False


def test_select_relevant_fallback_is_capped():
    cards = [{"id": f"role-{index}", "search": "無關", "line": str(index)} for index in range(20)]
    chosen, omitted = select_relevant("zzzz", cards, limit=3)
    assert len(chosen) == 3
    assert omitted == 17
    assert all(card["low_relevance"] for card in chosen)


def test_role_cards_drop_disabled_and_system_prompt(monkeypatch):
    config = BUILTIN_TEMPLATES["quick_task"]
    first = next(iter(config.roles)).value

    def fake_runtime(role_id: str):
        if role_id == first:
            return {"enabled": False, "name": "停用", "system_prompt": "SECRET-PROMPT"}
        return {
            "enabled": True,
            "name": role_id,
            "system_prompt": "SECRET-PROMPT-DO-NOT-LEAK",
        }

    monkeypatch.setattr("backend.company.role_catalog.resolve_runtime", fake_runtime)
    cards = query_role_cards(config)
    blob = "\n".join(card["line"] + card["search"] for card in cards)
    assert first not in {card["id"] for card in cards}
    assert "SECRET-PROMPT" not in blob
    assert "人天單價未登記" in cards[0]["line"]


def test_context_pack_filters_by_task_and_hides_secrets(monkeypatch):
    monkeypatch.setattr(
        "backend.company.manager_briefing.read_host_resources",
        lambda: {"available": False, "error": "測試"},
    )
    monkeypatch.setattr(
        "backend.company.manager_briefing.query_role_cards",
        lambda config: [
            {"id": "ui_designer", "search": "登入頁面 視覺", "line": "ui_designer｜視覺"},
            {"id": "plc_engineer", "search": "plc 連鎖", "line": "plc_engineer｜產線"},
        ],
    )
    monkeypatch.setattr(
        "backend.company.manager_briefing.query_skill_cards",
        lambda skills: [
            {
                "id": "page-skill",
                "roles": (),
                "search": "登入頁面",
                "line": "page-skill｜做頁面",
            },
            {
                "id": "plc-skill",
                "roles": ("plc_engineer",),
                "search": "plc",
                "line": "plc-skill｜產線技能",
            },
        ],
    )
    monkeypatch.setattr(
        "backend.company.manager_briefing.query_mcp_cards",
        lambda servers: [
            {"id": "pages", "search": "登入頁面", "line": "pages｜頁面 MCP"},
            {"id": "plant", "search": "plc", "line": "plant｜產線 MCP"},
        ],
    )
    monkeypatch.setattr(
        "backend.company.manager_briefing.query_tool_cards",
        lambda tools: [
            {
                "id": "layout_tool",
                "allowed_roles": ["ui_designer"],
                "search": "登入頁面",
                "line": "layout_tool｜佈局",
            },
            {
                "id": "valve_tool",
                "allowed_roles": ["plc_engineer"],
                "search": "登入頁面",
                "line": "valve_tool｜閥門",
            },
        ],
    )
    pack = assemble_manager_context("做一個登入頁面", BUILTIN_TEMPLATES["quick_task"], _budget())
    text = pack["text"]
    assert "ui_designer｜視覺" in text
    assert "page-skill｜做頁面" in text
    assert "pages｜頁面 MCP" in text
    assert "layout_tool｜佈局" in text
    assert "plc_engineer｜產線" not in text
    assert "plc-skill" not in text
    assert "valve_tool" not in text
    assert "SECRET" not in text
    assert pack["omitted"]["roles"] == 1
    assert pack["valid_roles"] == "ui_designer"
    rendered = MANAGER_DECOMPOSE.format(
        context_pack=text,
        valid_roles=pack["valid_roles"],
        task_budget=2,
        active_tier=0,
    )
    assert "【候選角色】" in rendered
    assert "feasibility" in rendered
    assert "不能當成已經下達" in rendered or "草案" in MANAGER_DECOMPOSE or "labor_note" in rendered


def test_full_template_pack_stays_within_top_n(monkeypatch):
    monkeypatch.setattr(
        "backend.company.manager_briefing.read_host_resources",
        lambda: {"available": False, "error": "測試"},
    )
    pack = assemble_manager_context("zzzz-no-overlap", BUILTIN_TEMPLATES["full_company"], _budget())
    assert len(pack["role_ids"]) <= TOP_ROLES
    assert pack["omitted"]["roles"] > 0
    assert pack["low_relevance"] is True
    assert "未送出" in pack["text"]


@pytest.mark.asyncio
async def test_llm_decompose_submits_context_pack_only(monkeypatch):
    from backend.company.decomposer import TaskDecomposer

    captured: dict[str, str] = {}

    def fake_call(prompt, system=None, model=None, **kwargs):
        captured["prompt"] = prompt
        captured["system"] = system or ""
        return json.dumps({
            "feasibility": "go",
            "execution_plan": "先做頁面",
            "budget_draft": {"model_usd": 0.1, "cloud_usd": None, "labor_note": "ui", "assumptions": ["無人天單價"]},
            "risks": ["範圍可能擴大"],
            "subtasks": [{
                "title": "頁面",
                "description": "用 page-skill",
                "assignee": "ui_designer",
                "depends_on": [],
                "complexity": "low",
                "phase": 1,
            }],
        })

    monkeypatch.setattr("backend.company.decomposer.call_llm", fake_call)
    monkeypatch.setattr(
        "backend.company.manager_briefing.assemble_manager_context",
        lambda goal, config, budget: {
            "text": "【候選角色】\nui_designer｜視覺\nSECRET-SHOULD-NOT-BE-ADDED-BY-DECOMPOSER",
            "valid_roles": "ui_designer",
            "omitted": {"roles": 70, "skills": 3, "mcp": 1, "tools": 4},
            "role_ids": ["ui_designer"],
            "low_relevance": False,
        },
    )
    decomposer = TaskDecomposer(BUILTIN_TEMPLATES["quick_task"], _budget())
    result = await decomposer._llm_decompose("做登入頁面")
    assert result.subtasks[0]["assignee"] == "ui_designer"
    assert result.meta["draft"] is True
    assert result.meta["feasibility"] == "go"
    assert result.meta["budget_draft"]["labor_note"] == "ui"
    assert result.meta["context_omitted"]["roles"] == 70
    assert "【候選角色】" in captured["prompt"]
    assert "ui_designer" in captured["prompt"]
    assert "全量目錄" in captured["system"]
    assert "組織架構與可用角色" not in captured["prompt"]
