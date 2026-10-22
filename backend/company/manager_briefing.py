"""任務經理拆解前的現場簡報。

呼叫大模型前附上三件事：系統當時可用的資源、本次模板裡啟用角色的上下文、
已啟用的技能與 MCP／內建工具。讀取失敗時改成一行說明，不中斷拆解。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ROLE_EXCERPT = 180
_SKILL_HINT = 120
_MAX_ROLES = 48
_MAX_SKILLS = 30
_MAX_MCP = 20
_MAX_TOOLS = 40


def _clip(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _gb(nbytes: float | int | None) -> str:
    try:
        return f"{float(nbytes or 0) / (1024 ** 3):.1f} GB"
    except (TypeError, ValueError):
        return "—"


def format_resource_brief(budget: Any, host: dict[str, Any] | None) -> str:
    """預算上限、模型層級與主機讀數。"""
    config = getattr(budget, "config", None)
    lines: list[str] = []
    if config is not None:
        task_limit = float(getattr(config, "task_limit_usd", 0) or 0)
        session_limit = float(getattr(config, "session_limit_usd", 0) or 0)
        monthly_limit = float(getattr(config, "monthly_limit_usd", 0) or 0)
        hard_stop = bool(getattr(config, "hard_stop", False))
        lines.append(
            "預算：任務上限 "
            f"${task_limit:.2f}；會話上限 ${session_limit:.2f}；月上限 ${monthly_limit:.2f}"
            f"（0 表示不限）。超限時{'停止' if hard_stop else '改用較便宜模型並繼續'}。"
        )
        spent = float(getattr(budget, "task_spent", 0) or 0)
        pressure = float(getattr(budget, "budget_pressure", 0) or 0)
        lines.append(f"本任務已花費 ${spent:.4f}；預算壓力 {pressure * 100:.0f}%。")
        docker = float(getattr(budget, "docker_cost", 0) or 0)
        aliyun = float(getattr(budget, "aliyun_cost", 0) or 0)
        lines.append(f"雲資源已記入：Docker ${docker:.4f}；阿里雲 ${aliyun:.4f}。")
        models = getattr(config, "tier_models", None) or {}
        if models:
            route = "、".join(
                f"{getattr(tier, 'value', tier)}→{model}" for tier, model in models.items()
            )
            lines.append(f"模型層級：{route}。")
    else:
        lines.append("預算設定不可用。")

    if not host or not host.get("available"):
        reason = (host or {}).get("error") or "未採集"
        lines.append(f"主機讀數不可用（{reason}）。")
        return "\n".join(lines)

    lines.append(
        "主機："
        f"CPU {host.get('cpu_percent', '—')}%（{host.get('cpu_count', '—')} 核）；"
        f"記憶體 {host.get('mem_percent', '—')}%"
        f"（可用 {_gb(host.get('mem_available'))} / 共 {_gb(host.get('mem_total'))}）；"
        f"磁碟 {host.get('disk_percent', '—')}%（剩餘 {_gb(host.get('disk_free'))}）。"
    )
    if host.get("net_percent") is not None:
        assumed = "（鏈路速率為估計）" if host.get("net_link_assumed") else ""
        lines.append(f"網路占用 {host.get('net_percent')}%{assumed}。")
    return "\n".join(lines)


def format_role_brief(config: Any) -> str:
    """本次模板中啟用角色的職責與系統提示摘要。"""
    roles = getattr(config, "roles", None) or {}
    lines: list[str] = []
    disabled: list[str] = []
    shown = 0
    for role_type, definition in roles.items():
        role_id = getattr(role_type, "value", str(role_type))
        runtime: dict[str, Any] = {}
        try:
            from backend.company.role_catalog import resolve_runtime

            runtime = resolve_runtime(role_id) or {}
        except Exception:
            runtime = {}
        if runtime.get("enabled") is False:
            disabled.append(role_id)
            continue
        if shown >= _MAX_ROLES:
            continue
        shown += 1
        name = str(runtime.get("name") or getattr(definition, "name", role_id))
        level = getattr(definition, "level", "")
        tier = getattr(getattr(definition, "default_tier", None), "value", "")
        parallel = getattr(definition, "max_parallel_work", "")
        duties = "；".join(list(getattr(definition, "responsibilities", []) or [])[:4]) or "未列職責"
        prompt = str(runtime.get("system_prompt") or getattr(definition, "system_prompt", "") or "")
        context = _clip(prompt, _ROLE_EXCERPT) if prompt.strip() else "沒有額外系統提示，沿用職責"
        preferred = str(runtime.get("preferred_model") or "").strip()
        lines.append(
            f"- {role_id}｜{name}｜Level {level}｜預設層級 {tier or '—'}｜並行 {parallel}"
        )
        lines.append(f"  職責：{duties}")
        lines.append(f"  上下文：{context}")
        if preferred:
            lines.append(f"  偏好模型：{preferred}")
    hidden = max(0, len(roles) - len(disabled) - shown)
    if hidden:
        lines.append(f"另有 {hidden} 個啟用角色未展開。")
    if disabled:
        lines.append("已停用、不可指派：" + "、".join(disabled))
    if not lines:
        return "（本次模板沒有可指派的角色）"
    return "\n".join(lines)


def format_skill_brief(skills: list[Any]) -> str:
    """已啟用技能的名稱、適用時機與角色範圍。不附完整內文。"""
    enabled = [s for s in skills if getattr(s, "enabled", True)]
    if not enabled:
        return "（目前沒有啟用的技能。不要假設未列出的技能可用。）"
    lines: list[str] = []
    for skill in enabled[:_MAX_SKILLS]:
        roles = list(getattr(skill, "roles", []) or [])
        scope = "、".join(roles) if roles else "全部啟用角色"
        trigger = _clip(str(getattr(skill, "trigger", "") or ""), _SKILL_HINT)
        hint = trigger or _clip(
            str(getattr(skill, "description", "") or getattr(skill, "content", "") or ""),
            _SKILL_HINT,
        )
        kind = str(getattr(skill, "skill_type", "") or "custom")
        lines.append(
            f"- {getattr(skill, 'id', '')}｜{getattr(skill, 'name', '')}｜{kind}｜角色：{scope}"
        )
        if hint:
            lines.append(f"  適用：{hint}")
    extra = max(0, len(enabled) - _MAX_SKILLS)
    if extra:
        lines.append(f"另有 {extra} 個啟用技能未展開。執行該席位時才注入技能內文。")
    else:
        lines.append("技能全文在席位執行時注入，這裡只列目錄。")
    return "\n".join(lines)


def format_mcp_brief(servers: list[Any], tools: list[Any]) -> str:
    """已啟用 MCP 與內建工具名。不附連線指令、網址或標頭。"""
    lines: list[str] = []
    enabled = [s for s in servers if getattr(s, "enabled", False)]
    if not enabled:
        lines.append("MCP：（目前沒有啟用的 MCP server。）")
    else:
        lines.append("MCP：")
        for server in enabled[:_MAX_MCP]:
            allow = list(getattr(server, "allowed_tools", []) or [])
            allow_text = "、".join(str(name) for name in allow) if allow else "未限制白名單，執行時才連線列工具"
            mode = "唯讀" if getattr(server, "readonly", True) else "可寫"
            transport = getattr(server, "transport", "") or "stdio"
            lines.append(
                f"- {getattr(server, 'id', '')}｜{getattr(server, 'name', '')}｜{transport}｜{mode}｜工具：{allow_text}"
            )
        extra = len(enabled) - _MAX_MCP
        if extra:
            lines.append(f"另有 {extra} 個啟用 MCP 未展開。")
    names: list[str] = []
    for tool in tools[:_MAX_TOOLS]:
        name = str(getattr(tool, "name", "") or "")
        if not name:
            continue
        desc = _clip(str(getattr(tool, "description", "") or ""), 60)
        names.append(f"{name}（{desc}）" if desc else name)
    if names:
        lines.append("內建工具：" + "；".join(names))
        extra_tools = max(0, len(tools) - _MAX_TOOLS)
        if extra_tools:
            lines.append(f"另有 {extra_tools} 個內建工具未展開。")
    else:
        lines.append("內建工具：（沒有已註冊工具）")
    return "\n".join(lines)


def read_host_resources() -> dict[str, Any]:
    """主機 CPU／記憶體／磁碟。失敗回 available=False。"""
    try:
        from backend.services.docker_manager import get_docker_manager

        host = get_docker_manager().host_stats()
        return host if isinstance(host, dict) else {"available": False, "error": "讀數格式異常"}
    except Exception as exc:
        logger.debug("任務經理讀主機資源失敗：%s", exc)
        return {"available": False, "error": str(exc)}


def collect_manager_briefing(config: Any, budget: Any) -> dict[str, str]:
    """組裝要放進任務經理提示詞的四段文字。"""
    host = read_host_resources()
    resources = format_resource_brief(budget, host)

    try:
        roles = format_role_brief(config)
    except Exception as exc:
        logger.debug("任務經理讀角色上下文失敗：%s", exc)
        roles = "（角色上下文讀取失敗）"

    try:
        from backend.company.skills import skills_store

        skills = format_skill_brief(skills_store.enabled_for(None))
    except Exception as exc:
        logger.debug("任務經理讀技能目錄失敗：%s", exc)
        skills = "（技能目錄讀取失敗）"

    try:
        from backend.company.mcp_clients import mcp_registry
        from backend.company.tools import tool_registry

        mcp_tools = format_mcp_brief(mcp_registry.list(), tool_registry.list_tools())
    except Exception as exc:
        logger.debug("任務經理讀 MCP／工具失敗：%s", exc)
        mcp_tools = "（MCP 與工具目錄讀取失敗）"

    return {
        "resources": resources,
        "roles": roles,
        "skills": skills,
        "mcp_tools": mcp_tools,
    }
