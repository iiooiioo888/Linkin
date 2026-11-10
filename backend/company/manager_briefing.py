"""任務經理的目錄與上下文包。

目錄可查：資源快照、角色能力卡、MCP／技能註冊項。
送給大模型的是組裝後的最小上下文包：只含與本次目標相關、
已啟用、且去掉秘密與全文的 Top-N 候選。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

TOP_ROLES = 8
TOP_SKILLS = 6
TOP_MCP = 5
TOP_TOOLS = 8
_LINE = 160

_CJK_CHUNK = re.compile(r"[\u4e00-\u9fff]{2,}")
_ASCII_WORD = re.compile(r"[a-z0-9_]{2,}")


def _clip(text: str, limit: int = _LINE) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _gb(nbytes: float | None) -> str:
    try:
        return f"{float(nbytes or 0) / (1024 ** 3):.1f} GB"
    except (TypeError, ValueError):
        return "—"


def goal_tokens(goal: str) -> set[str]:
    """目標裡的詞。中文取連續字，不做全切，避免雙字碎詞誤配。"""
    tokens = set(_ASCII_WORD.findall((goal or "").lower()))
    tokens.update(_CJK_CHUNK.findall(goal or ""))
    return tokens


def _contains_term(hay: str, token: str) -> bool:
    if re.fullmatch(r"[a-z0-9_]+", token):
        return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", hay) is not None
    return token in hay


def _score(goal: str, blob: str) -> int:
    """目標與條目雙向重合。英文要整詞，避免 no 命中 monitor。"""
    goal_l = (goal or "").lower()
    blob_l = (blob or "").lower()
    score = 0
    seen: set[str] = set()
    for token in goal_tokens(goal) | goal_tokens(blob):
        key = token.lower()
        if key in seen or len(key) < 2:
            continue
        seen.add(key)
        if _contains_term(goal_l, key) and _contains_term(blob_l, key):
            score += min(len(key), 8)
    return score


def select_relevant(goal: str, cards: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    """依目標用詞取 Top-N。完全對不上時，只回目錄前 N 張並標低相關。"""
    scored: list[dict[str, Any]] = []
    for card in cards:
        row = dict(card)
        row["score"] = _score(goal, str(card.get("search") or ""))
        row["low_relevance"] = False
        scored.append(row)
    scored.sort(key=lambda row: (-int(row["score"]), str(row.get("id") or "")))
    if scored and int(scored[0]["score"]) > 0:
        chosen = [row for row in scored if int(row["score"]) > 0][:limit]
    else:
        chosen = []
        for row in scored[:limit]:
            row["low_relevance"] = True
            chosen.append(row)
    return chosen, max(0, len(cards) - len(chosen))


def _runtime(role_id: str) -> dict[str, Any]:
    try:
        from backend.company.role_catalog import resolve_runtime

        runtime = resolve_runtime(role_id)
        return runtime if isinstance(runtime, dict) else {}
    except Exception:
        return {}


def query_role_cards(config: Any) -> list[dict[str, Any]]:
    """啟用角色的能力卡。系統提示全文只用於目錄，不進上下文包。"""
    cards: list[dict[str, Any]] = []
    for role_type, definition in (getattr(config, "roles", None) or {}).items():
        role_id = getattr(role_type, "value", str(role_type))
        runtime = _runtime(role_id)
        if runtime.get("enabled") is False:
            continue
        name = str(runtime.get("name") or getattr(definition, "name", role_id))
        duties = [str(item) for item in (getattr(definition, "responsibilities", None) or [])[:4]]
        delegates = [
            getattr(item, "value", str(item))
            for item in (getattr(definition, "can_delegate_to", None) or [])[:4]
        ]
        tier = getattr(getattr(definition, "default_tier", None), "value", "") or "—"
        level = getattr(definition, "level", "")
        search = " ".join([role_id, name, *duties, *delegates])
        cards.append({
            "id": role_id,
            "name": name,
            "level": level,
            "tier": tier,
            "duties": duties,
            "delegates": delegates,
            "search": search,
            "line": _clip(
                f"{role_id}｜{name}｜Level {level}｜模型層級 {tier}｜"
                f"職責：{'；'.join(duties) or '未列'}｜"
                f"協作：{'、'.join(delegates) or '未列'}｜"
                "負載未登記｜人天單價未登記"
            ),
        })
    return cards


def query_skill_cards(skills: list[Any]) -> list[dict[str, Any]]:
    """已啟用技能的註冊項。不收錄內文。"""
    cards: list[dict[str, Any]] = []
    for skill in skills:
        if getattr(skill, "enabled", True) is False:
            continue
        roles = tuple(str(role) for role in (getattr(skill, "roles", None) or []))
        name = str(getattr(skill, "name", "") or getattr(skill, "id", ""))
        trigger = _clip(str(getattr(skill, "trigger", "") or getattr(skill, "description", "") or ""), 80)
        kind = str(getattr(skill, "skill_type", "") or "custom")
        skill_id = str(getattr(skill, "id", "") or name)
        scope = "、".join(roles) if roles else "本次候選角色"
        cards.append({
            "id": skill_id,
            "roles": roles,
            "search": " ".join([skill_id, name, kind, trigger, *roles]),
            "line": _clip(f"{skill_id}｜{name}｜{kind}｜角色：{scope}｜適用：{trigger or '未列'}｜調用成本未登記"),
        })
    return cards


def query_mcp_cards(servers: list[Any]) -> list[dict[str, Any]]:
    """已啟用 MCP。不收錄指令、網址、環境變數、標頭。"""
    cards: list[dict[str, Any]] = []
    for server in servers:
        if not getattr(server, "enabled", False):
            continue
        allow = [str(name) for name in (getattr(server, "allowed_tools", None) or [])]
        allow_text = "、".join(allow) if allow else "白名單未限制，執行時才連線"
        mode = "唯讀" if getattr(server, "readonly", True) else "可寫"
        server_id = str(getattr(server, "id", "") or "")
        name = str(getattr(server, "name", "") or server_id)
        transport = str(getattr(server, "transport", "") or "stdio")
        cards.append({
            "id": server_id,
            "search": " ".join([server_id, name, transport, *allow]),
            "line": _clip(f"{server_id}｜{name}｜{transport}｜{mode}｜工具：{allow_text}｜延遲與費用未登記"),
        })
    return cards


def query_tool_cards(tools: list[Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "")
        if not name:
            continue
        allowed = [str(role) for role in (getattr(tool, "allowed_roles", None) or [])]
        desc = _clip(str(getattr(tool, "description", "") or ""), 60)
        mode = "只讀" if getattr(tool, "readonly", True) else "可寫"
        cards.append({
            "id": name,
            "allowed_roles": allowed,
            "search": " ".join([name, desc, *allowed]),
            "line": _clip(f"{name}｜{mode}｜{desc or '無描述'}"),
        })
    return cards


def _tool_visible(card: dict[str, Any], role_ids: set[str]) -> bool:
    allowed = set(card.get("allowed_roles") or [])
    if not allowed:
        return True
    return bool(allowed & role_ids)


def resource_snapshot(budget: Any, host: dict[str, Any] | None) -> str:
    """資源快照：上限、層級單價、主機概況。不含帳單明細。"""
    lines: list[str] = []
    config = getattr(budget, "config", None)
    if config is None:
        lines.append("預算上限未登記。")
    else:
        hard_stop = bool(getattr(config, "hard_stop", False))
        pressure = float(getattr(budget, "budget_pressure", 0) or 0)
        lines.append(
            "配額：任務 $"
            f"{float(getattr(config, 'task_limit_usd', 0) or 0):.2f}；"
            f"會話 ${float(getattr(config, 'session_limit_usd', 0) or 0):.2f}；"
            f"月 ${float(getattr(config, 'monthly_limit_usd', 0) or 0):.2f}。"
            f"壓力 {pressure * 100:.0f}%。"
            f"超限時{'停止' if hard_stop else '改用較便宜模型並繼續'}。"
        )
        models = getattr(config, "tier_models", None) or {}
        prices: list[str] = []
        try:
            from backend.company.rate_card import get_model_rate_cards, rate_card_for

            known = get_model_rate_cards()
        except Exception:
            known = {}
            rate_card_for = None  # type: ignore[assignment]
        for tier, model in models.items():
            model_name = str(model)
            bare = model_name.split("/")[-1]
            if rate_card_for is None or (model_name not in known and bare not in known):
                prices.append(f"{getattr(tier, 'value', tier)}→{model_name} 單價未登記")
                continue
            card = rate_card_for(model_name)
            prices.append(
                f"{getattr(tier, 'value', tier)}→{model_name} "
                f"輸入 ${float(card.get('input') or 0):.2f}/輸出 ${float(card.get('output') or 0):.2f}（每 1M tokens）"
            )
        if prices:
            lines.append("模型：" + "；".join(prices) + "。")
    try:
        from backend.company.docker_tools import DOCKER_SERVICE_HOURLY_RATES

        rates = "、".join(
            f"{name} ${rate:.3f}/時" for name, rate in DOCKER_SERVICE_HOURLY_RATES.items()
        )
        lines.append(f"雲單價摘要：{rates}。這是費率，不是主機清單或可用區。")
    except Exception:
        lines.append("雲單價未登記。")
    if not host or not host.get("available"):
        lines.append(f"主機快照不可用（{(host or {}).get('error') or '未採集'}）。")
    else:
        lines.append(
            "主機快照："
            f"CPU {host.get('cpu_percent', '—')}%／{host.get('cpu_count', '—')} 核；"
            f"記憶體 {host.get('mem_percent', '—')}%（可用 {_gb(host.get('mem_available'))}）；"
            f"磁碟剩餘 {_gb(host.get('disk_free'))}。"
        )
    lines.append("未登記：人天單價、雲主機規格與數量、速率限制、許可證、測試環境、外部服務配額。")
    return "\n".join(lines)


def budget_rules_text() -> str:
    return (
        "模型費按公開價卡的各收費項乘用量，單位 USD。沒有 token 計數時，低／中／高複雜度分別按 500／2000／8000 token 的輸入加輸出粗估。\n"
        "雲資源按小時費率乘運行時長。預算壓力取任務、會話、月三個上限裡最高的使用率。\n"
        "這次拆解呼叫本身計入任務預算。程式沒有另設緩衝比例，估算不得超過任務上限。\n"
        "人天、加班與外部人力沒有單價，不要換算成金額。"
    )


def _merge_roles(goal: str, role_cards: list[dict[str, Any]], skills: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    picked_skills, _ = select_relevant(goal, skills, TOP_SKILLS)
    by_id = {card["id"]: card for card in role_cards}
    forced: list[dict[str, Any]] = []
    for skill in picked_skills:
        for role_id in skill.get("roles") or []:
            card = by_id.get(role_id)
            if card and card not in forced:
                forced.append(card)
    ranked, _ = select_relevant(goal, role_cards, TOP_ROLES)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in forced + ranked:
        if card["id"] in seen:
            continue
        seen.add(card["id"])
        merged.append(card)
        if len(merged) >= TOP_ROLES:
            break
    return merged, max(0, len(role_cards) - len(merged))


def render_context_pack(
    *,
    goal: str,
    constraints: str,
    resources: str,
    roles: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    mcp_servers: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    omitted: dict[str, int],
) -> str:
    low = any(card.get("low_relevance") for card in roles)
    role_note = "與任務用詞沒有重合，以下只是模板內啟用席位的前幾張能力卡。" if low else "只列與任務用詞重合、或被候選技能點名的席位。"
    sections = [
        "【任務】",
        _clip(goal, 500) or "（空）",
        "",
        "【約束】",
        constraints,
        "",
        "【資源快照】",
        resources,
        "",
        "【候選角色】",
        role_note,
        *([card["line"] for card in roles] or ["（沒有可指派的啟用角色）"]),
        f"目錄中另有 {omitted.get('roles', 0)} 個啟用角色未送出。",
        "",
        "【候選技能】",
        *([card["line"] for card in skills] or ["（沒有與任務相關的啟用技能）"]),
        f"目錄中另有 {omitted.get('skills', 0)} 個啟用技能未送出。技能全文不在本包。",
        "",
        "【候選 MCP】",
        *([card["line"] for card in mcp_servers] or ["（沒有與任務相關的啟用 MCP）"]),
        f"目錄中另有 {omitted.get('mcp', 0)} 個啟用 MCP 未送出。連線秘密不在本包。",
        "",
        "【候選工具】",
        *([card["line"] for card in tools] or ["（沒有候選角色可用的工具）"]),
        f"目錄中另有 {omitted.get('tools', 0)} 個工具未送出。",
        "",
        "【預算口徑】",
        budget_rules_text(),
    ]
    return "\n".join(sections)


def read_host_resources() -> dict[str, Any]:
    try:
        from backend.services.docker_manager import get_docker_manager

        host = get_docker_manager().host_stats()
        return host if isinstance(host, dict) else {"available": False, "error": "讀數格式異常"}
    except Exception as exc:
        logger.debug("任務經理讀主機資源失敗：%s", exc)
        return {"available": False, "error": str(exc)}


def assemble_manager_context(goal: str, config: Any, budget: Any) -> dict[str, Any]:
    """組裝本次拆解要用的上下文包。目錄查詢失敗時該段改為空，不中斷。"""
    host = read_host_resources()
    resources = resource_snapshot(budget, host)
    try:
        role_cards = query_role_cards(config)
    except Exception as exc:
        logger.debug("角色目錄讀取失敗：%s", exc)
        role_cards = []
    try:
        from backend.company.skills import skills_store

        skill_cards = query_skill_cards(skills_store.enabled_for(None))
    except Exception as exc:
        logger.debug("技能目錄讀取失敗：%s", exc)
        skill_cards = []
    try:
        from backend.company.mcp_clients import mcp_registry

        mcp_cards = query_mcp_cards(mcp_registry.list())
    except Exception as exc:
        logger.debug("MCP 目錄讀取失敗：%s", exc)
        mcp_cards = []
    try:
        from backend.company.tools import tool_registry

        tool_cards = query_tool_cards(tool_registry.list_tools())
    except Exception as exc:
        logger.debug("工具目錄讀取失敗：%s", exc)
        tool_cards = []

    roles, omitted_roles = _merge_roles(goal, role_cards, skill_cards)
    role_ids = {card["id"] for card in roles}
    visible_skills = [
        card for card in skill_cards
        if not card.get("roles") or set(card["roles"]) & role_ids
    ]
    skills, omitted_skills_visible = select_relevant(goal, visible_skills, TOP_SKILLS)
    omitted_skills = omitted_skills_visible + (len(skill_cards) - len(visible_skills))
    mcp_servers, omitted_mcp = select_relevant(goal, mcp_cards, TOP_MCP)
    visible_tools = [card for card in tool_cards if _tool_visible(card, role_ids)]
    tools, omitted_tools_visible = select_relevant(goal, visible_tools, TOP_TOOLS)
    omitted_tools = omitted_tools_visible + (len(tool_cards) - len(visible_tools))
    omitted = {
        "roles": omitted_roles,
        "skills": omitted_skills,
        "mcp": omitted_mcp,
        "tools": omitted_tools,
    }
    limit = float(getattr(getattr(budget, "config", None), "task_limit_usd", 0) or 0)
    hard_stop = bool(getattr(getattr(budget, "config", None), "hard_stop", False))
    constraints = (
        f"任務預算上限 ${limit:.2f}。"
        f"超限時{'停止' if hard_stop else '降級後繼續'}。"
        "不可用：已停用角色、未啟用技能與 MCP、本包未列出的候選。"
        "不要假設人天單價、雲主機台數或未登記的配額。"
    )
    text = render_context_pack(
        goal=goal,
        constraints=constraints,
        resources=resources,
        roles=roles,
        skills=skills,
        mcp_servers=mcp_servers,
        tools=tools,
        omitted=omitted,
    )
    valid_roles = "/".join(card["id"] for card in roles) or "developer"
    return {
        "text": text,
        "valid_roles": valid_roles,
        "omitted": omitted,
        "role_ids": sorted(role_ids),
        "low_relevance": any(card.get("low_relevance") for card in roles),
    }
