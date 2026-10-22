"""任務經理拆解前提示詞要帶上資源、角色上下文、技能與 MCP。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.company.manager_briefing import (
    collect_manager_briefing,
    format_mcp_brief,
    format_resource_brief,
    format_role_brief,
    format_skill_brief,
)
from backend.company.prompts import MANAGER_DECOMPOSE
from backend.company.roles import BUILTIN_TEMPLATES


def _budget():
    from backend.company.budget import BudgetManager

    return BudgetManager(BUILTIN_TEMPLATES["quick_task"].budget)


def test_resource_brief_includes_limits_and_host():
    text = format_resource_brief(
        _budget(),
        {
            "available": True,
            "cpu_percent": 12.5,
            "cpu_count": 4,
            "mem_percent": 40.0,
            "mem_available": 3 * 1024 ** 3,
            "mem_total": 8 * 1024 ** 3,
            "disk_percent": 55.0,
            "disk_free": 20 * 1024 ** 3,
        },
    )
    assert "任務上限" in text
    assert "CPU 12.5%" in text
    assert "記憶體 40.0%" in text
    assert "磁碟 55.0%" in text


def test_resource_brief_when_host_unavailable():
    text = format_resource_brief(_budget(), {"available": False, "error": "psutil 未安裝"})
    assert "主機讀數不可用" in text
    assert "psutil 未安裝" in text


def test_role_brief_uses_runtime_context_and_skips_disabled(monkeypatch):
    config = BUILTIN_TEMPLATES["quick_task"]
    role_ids = [role.value for role in config.roles]

    def fake_runtime(role_id: str):
        if role_id == role_ids[0]:
            return {"enabled": False, "name": "停用席"}
        return {
            "enabled": True,
            "name": f"名稱-{role_id}",
            "system_prompt": "你負責把交付物寫成可驗收的規格。",
            "preferred_model": "gpt-test",
        }

    monkeypatch.setattr("backend.company.role_catalog.resolve_runtime", fake_runtime)
    text = format_role_brief(config)
    assert role_ids[0] in text
    assert "已停用、不可指派" in text
    assert "你負責把交付物寫成可驗收的規格" in text
    assert "偏好模型：gpt-test" in text
    assert f"- {role_ids[1]}｜名稱-{role_ids[1]}" in text


def test_skill_and_mcp_briefs_list_enabled_only_and_hide_secrets():
    skills = [
        SimpleNamespace(
            id="agent-reach",
            name="Agent Reach",
            enabled=True,
            roles=["crawler"],
            skill_type="cli-stub",
            trigger="需要讀公開網頁時",
            description="",
            content="FULL-SECRET-BODY",
        ),
        SimpleNamespace(
            id="off",
            name="關閉技能",
            enabled=False,
            roles=[],
            skill_type="custom",
            trigger="",
            description="",
            content="",
        ),
    ]
    skill_text = format_skill_brief(skills)
    assert "agent-reach" in skill_text
    assert "需要讀公開網頁時" in skill_text
    assert "關閉技能" not in skill_text
    assert "FULL-SECRET-BODY" not in skill_text

    servers = [
        SimpleNamespace(
            id="local",
            name="本地 MCP",
            enabled=True,
            transport="stdio",
            readonly=True,
            allowed_tools=["search"],
            command="curl https://secret.example/token",
            url="https://secret.example",
            env={"API_KEY": "hidden"},
            headers={"Authorization": "Bearer hidden"},
        ),
        SimpleNamespace(
            id="paused",
            name="停用 MCP",
            enabled=False,
            transport="http",
            readonly=True,
            allowed_tools=[],
        ),
    ]
    tools = [SimpleNamespace(name="web_search", description="搜尋公開網頁")]
    mcp_text = format_mcp_brief(servers, tools)
    assert "本地 MCP" in mcp_text
    assert "search" in mcp_text
    assert "web_search" in mcp_text
    assert "停用 MCP" not in mcp_text
    assert "secret.example" not in mcp_text
    assert "hidden" not in mcp_text
    assert "Bearer" not in mcp_text


def test_collect_manager_briefing_assembles_sections(monkeypatch):
    monkeypatch.setattr(
        "backend.company.manager_briefing.read_host_resources",
        lambda: {"available": False, "error": "測試"},
    )
    monkeypatch.setattr(
        "backend.company.manager_briefing.format_role_brief",
        lambda config: "角色：developer",
    )
    monkeypatch.setattr(
        "backend.company.skills.skills_store.enabled_for",
        lambda role: [],
    )
    monkeypatch.setattr(
        "backend.company.mcp_clients.mcp_registry.list",
        lambda: [],
    )
    monkeypatch.setattr(
        "backend.company.tools.tool_registry.list_tools",
        lambda: [SimpleNamespace(name="web_search", description="搜尋")],
    )
    brief = collect_manager_briefing(BUILTIN_TEMPLATES["quick_task"], _budget())
    assert "主機讀數不可用" in brief["resources"]
    assert brief["roles"] == "角色：developer"
    assert "沒有啟用的技能" in brief["skills"]
    assert "web_search" in brief["mcp_tools"]
    rendered = MANAGER_DECOMPOSE.format(
        goal="做一頁",
        resources=brief["resources"],
        org_chart="org",
        role_descriptions=brief["roles"],
        skills=brief["skills"],
        mcp_tools=brief["mcp_tools"],
        task_budget=2,
        active_tier=0,
        valid_roles="developer",
    )
    assert "【系統可用資源】" in rendered
    assert "【可用技能】" in rendered
    assert "【可用 MCP 與工具】" in rendered
    assert "角色：developer" in rendered


@pytest.mark.asyncio
async def test_llm_decompose_submits_briefing(monkeypatch):
    from backend.company.decomposer import TaskDecomposer

    captured: dict[str, str] = {}

    def fake_call(prompt, system=None, model=None, **kwargs):
        captured["prompt"] = prompt
        captured["system"] = system or ""
        return json.dumps({
            "execution_plan": "先分析",
            "subtasks": [{
                "title": "分析",
                "description": "規格",
                "assignee": "developer",
                "depends_on": [],
                "complexity": "low",
                "phase": 1,
            }],
        })

    monkeypatch.setattr("backend.company.decomposer.call_llm", fake_call)
    monkeypatch.setattr(
        "backend.company.manager_briefing.collect_manager_briefing",
        lambda config, budget: {
            "resources": "CPU 3%",
            "roles": "developer 上下文：寫規格",
            "skills": "技能：agent-reach",
            "mcp_tools": "MCP：mine",
        },
    )
    config = BUILTIN_TEMPLATES["quick_task"]
    decomposer = TaskDecomposer(config, _budget())
    result = await decomposer._llm_decompose("建立登入頁")
    assert result.subtasks[0]["assignee"] == "developer"
    assert "CPU 3%" in captured["prompt"]
    assert "developer 上下文：寫規格" in captured["prompt"]
    assert "技能：agent-reach" in captured["prompt"]
    assert "MCP：mine" in captured["prompt"]
    assert "可用資源" in captured["system"]
