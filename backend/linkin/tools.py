"""靈境工具封裝層：參數校驗、單工具鐵律、敏感操作二次確認。"""

from __future__ import annotations

import re
from typing import Any

from backend.linkin.constitution import (
    allowed_styles_for_region,
    item_balance,
    max_blocks_per_call,
)

MAX_BLOCKS = 5000
SIMILARITY_THRESHOLD = 0.75
QUALITY_THRESHOLD = 80

TOOL_BUILDER_GENERATE = "BuilderAI.generate"
TOOL_NPC_CREATE = "NPC.create"
TOOL_NPC_DIALOGUE = "NPC.dialogue"
TOOL_QUEST_GENERATE = "Quest.generate"
TOOL_ITEM_CREATE = "Item.create"
TOOL_ADMIN_EXECUTE = "Admin.execute"

ALLOWED_TOOLS = frozenset(
    {
        TOOL_BUILDER_GENERATE,
        TOOL_NPC_CREATE,
        TOOL_NPC_DIALOGUE,
        TOOL_QUEST_GENERATE,
        TOOL_ITEM_CREATE,
        TOOL_ADMIN_EXECUTE,
    }
)

QUEST_TYPES = frozenset({"主线", "支线", "日常", "主線", "支線"})
ITEM_TYPES = frozenset({"武器", "防具", "消耗品"})
DIFFICULTIES = frozenset({"简单", "普通", "困难", "簡單", "困難", "easy", "normal", "hard"})

COMMAND_CHAIN_TOKENS = ("&&", ";", "|", "\n&&", "；")
COMMAND_CHAIN_RE = re.compile(r"(&&|;|\n\s*&&|\s\|\s)")

SENSITIVE_ADMIN_RE = re.compile(
    r"("
    r"kick|ban|pardon|op\b|deop|stop|restart|whitelist|gamemode|difficulty|"
    r"worldborder|save-off|save-on|op-permission|whitelist|"
    r"踢出|封禁|停服|重啟|重启|修改世界|管理員|管理员|白名單|白名单"
    r")",
    re.IGNORECASE,
)


class ToolValidationError(ValueError):
    """工具參數或鐵律校驗失敗。"""

    def __init__(self, message: str, *, code: str = "invalid", extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _walk_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_walk_strings(item))
    return found


def validate_no_command_chain(payload: Any) -> None:
    for text in _walk_strings(payload):
        if COMMAND_CHAIN_RE.search(text):
            raise ToolValidationError(
                "禁止使用命令鏈（&&、;、|）。單次響應僅限一個工具。",
                code="command_chain",
            )


def validate_single_tool(tool_name: str, extra_tools: list[str] | None = None) -> None:
    extras = [str(t).strip() for t in (extra_tools or []) if str(t).strip()]
    if extras:
        raise ToolValidationError(
            "單次響應僅限調用一個工具，禁止命令鏈或多工具並行。",
            code="multi_tool",
            extra={"tools": [tool_name, *extras]},
        )
    if tool_name not in ALLOWED_TOOLS:
        raise ToolValidationError(f"未知工具：{tool_name}", code="unknown_tool")


def validate_builder_generate(params: dict[str, Any]) -> dict[str, Any]:
    prompt = _as_text(params.get("prompt")).strip()
    style = _as_text(params.get("style")).strip()
    location = params.get("location")
    region = _as_text(params.get("region")).strip()
    if not prompt:
        raise ToolValidationError("BuilderAI.generate 需要 prompt")
    if not style:
        raise ToolValidationError("BuilderAI.generate 需要 style")
    if location is None or _as_text(location).strip() == "":
        raise ToolValidationError("BuilderAI.generate 需要 location")

    raw_blocks = params.get("block_count", params.get("blocks"))
    if raw_blocks is None:
        block_count = min(MAX_BLOCKS, max(16, len(prompt) * 4))
    else:
        try:
            block_count = int(raw_blocks)
        except (TypeError, ValueError) as exc:
            raise ToolValidationError("block_count 必須為整數") from exc
    limit = max_blocks_per_call() or MAX_BLOCKS
    if block_count > limit or block_count > MAX_BLOCKS:
        raise ToolValidationError(
            f"單次生成不得超過 {min(limit, MAX_BLOCKS)} 方塊（收到 {block_count}）",
            code="block_limit",
            extra={"block_count": block_count, "max_blocks": min(limit, MAX_BLOCKS)},
        )
    if block_count <= 0:
        raise ToolValidationError("block_count 必須為正整數", code="block_limit")

    if not region and isinstance(location, str):
        region = location.strip()
    allowed = allowed_styles_for_region(region) if region else None
    if allowed is not None and style not in allowed:
        raise ToolValidationError(
            f"風格「{style}」與區域「{region}」文化不符。允許：{'、'.join(allowed)}",
            code="style_mismatch",
            extra={"style": style, "region": region, "allowed_styles": allowed},
        )
    return {
        "prompt": prompt,
        "style": style,
        "location": location,
        "region": region,
        "block_count": block_count,
    }


def validate_npc_create(params: dict[str, Any]) -> dict[str, Any]:
    card = params.get("characterCard") or params.get("character_card") or params
    if not isinstance(card, dict):
        raise ToolValidationError("NPC.create 需要完整角色卡物件")
    name = _as_text(card.get("name")).strip()
    backstory = _as_text(card.get("backstory") or card.get("background")).strip()
    personality = _as_text(card.get("personality")).strip()
    if not name:
        raise ToolValidationError("角色卡缺少 name")
    if not backstory:
        raise ToolValidationError("所有 NPC 必須擁有符合世界觀的背景故事，不可為空")
    if not personality:
        raise ToolValidationError("角色卡缺少 personality")
    return {
        "id": _as_text(card.get("id")).strip() or None,
        "name": name,
        "faction": _as_text(card.get("faction")).strip(),
        "occupation": _as_text(card.get("occupation") or card.get("role")).strip(),
        "personality": personality,
        "backstory": backstory,
        "location": _as_text(card.get("location")).strip(),
        "speech_style": _as_text(card.get("speech_style") or card.get("speechStyle")).strip(),
        "relationships": card.get("relationships") if isinstance(card.get("relationships"), dict) else {},
    }


def validate_npc_dialogue(params: dict[str, Any]) -> dict[str, Any]:
    npc_id = _as_text(params.get("npcId") or params.get("npc_id") or params.get("id")).strip()
    message = _as_text(params.get("playerMessage") or params.get("message")).strip()
    if not npc_id:
        raise ToolValidationError("NPC.dialogue 需要 npcId")
    if not message:
        raise ToolValidationError("NPC.dialogue 需要 playerMessage")
    return {"npc_id": npc_id, "player_message": message}


def validate_quest_generate(params: dict[str, Any]) -> dict[str, Any]:
    player_id = _as_text(params.get("playerId") or params.get("player_id")).strip() or "anonymous"
    quest_type = _as_text(params.get("questType") or params.get("quest_type") or "支线").strip()
    difficulty = _as_text(params.get("difficulty") or "普通").strip()
    if quest_type not in QUEST_TYPES:
        raise ToolValidationError("questType 必須為 主线 / 支线 / 日常")
    normalized = {"主線": "主线", "支線": "支线"}.get(quest_type, quest_type)
    diff_map = {"簡單": "简单", "困難": "困难", "easy": "简单", "normal": "普通", "hard": "困难"}
    difficulty = diff_map.get(difficulty, difficulty)
    if difficulty not in {"简单", "普通", "困难"}:
        raise ToolValidationError("difficulty 必須為 简单 / 普通 / 困难")
    return {
        "player_id": player_id,
        "quest_type": normalized,
        "difficulty": difficulty,
        "region": _as_text(params.get("region")).strip(),
        "faction": _as_text(params.get("faction")).strip(),
    }


def _attr_score(attributes: Any) -> int:
    if isinstance(attributes, (int, float)):
        return int(attributes)
    if isinstance(attributes, dict):
        nums = [int(v) for v in attributes.values() if isinstance(v, (int, float))]
        return max(nums) if nums else 0
    return 0


def validate_item_create(params: dict[str, Any]) -> dict[str, Any]:
    name = _as_text(params.get("name")).strip()
    item_type = _as_text(params.get("type")).strip()
    attributes = params.get("attributes") or {}
    rarity = _as_text(params.get("rarity") or "common").strip().lower()
    if not name:
        raise ToolValidationError("Item.create 需要 name")
    if item_type not in ITEM_TYPES:
        raise ToolValidationError("type 必須為 武器 / 防具 / 消耗品")
    balance = item_balance()
    rarities = balance.get("rarities") or {}
    spec = rarities.get(rarity)
    if spec is None:
        raise ToolValidationError(f"未知稀有度：{rarity}")
    score = _attr_score(attributes)
    lo, hi = int(spec.get("attr_min", 0)), int(spec.get("attr_max", 70))
    if score and (score < lo or score > hi):
        raise ToolValidationError(
            f"屬性 {score} 超出 {rarity} 平衡區間 {lo}-{hi}",
            code="item_balance",
            extra={"rarity": rarity, "score": score, "min": lo, "max": hi},
        )
    return {
        "name": name,
        "type": item_type,
        "attributes": attributes if isinstance(attributes, dict) else {"power": attributes},
        "rarity": rarity,
        "description": _as_text(params.get("description")).strip(),
    }


def is_sensitive_admin(command: str) -> bool:
    return bool(SENSITIVE_ADMIN_RE.search(command or ""))


def validate_admin_execute(params: dict[str, Any], *, confirmed: bool = False) -> dict[str, Any]:
    command = _as_text(params.get("command")).strip()
    if not command:
        raise ToolValidationError("Admin.execute 需要 command")
    confirm_flag = confirmed or bool(params.get("confirmed") or params.get("confirm"))
    if is_sensitive_admin(command) and not confirm_flag:
        raise ToolValidationError(
            "敏感操作需二次確認（踢出玩家、修改世界設定、停服等）",
            code="needs_confirmation",
            extra={"needs_confirmation": True, "command": command},
        )
    return {"command": command, "confirmed": confirm_flag, "sensitive": is_sensitive_admin(command)}


_VALIDATORS = {
    TOOL_BUILDER_GENERATE: lambda p, **kw: validate_builder_generate(p),
    TOOL_NPC_CREATE: lambda p, **kw: validate_npc_create(p),
    TOOL_NPC_DIALOGUE: lambda p, **kw: validate_npc_dialogue(p),
    TOOL_QUEST_GENERATE: lambda p, **kw: validate_quest_generate(p),
    TOOL_ITEM_CREATE: lambda p, **kw: validate_item_create(p),
    TOOL_ADMIN_EXECUTE: lambda p, **kw: validate_admin_execute(p, confirmed=kw.get("confirmed", False)),
}


def invoke_tool(
    tool_name: str,
    params: dict[str, Any] | None = None,
    *,
    extra_tools: list[str] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """校驗並回傳正規化參數（不直接改世界；由 API / 知識層執行）。"""
    params = params or {}
    validate_single_tool(tool_name, extra_tools)
    validate_no_command_chain({"tool": tool_name, **params})
    validator = _VALIDATORS[tool_name]
    normalized = validator(params, confirmed=confirmed)
    return {"tool": tool_name, "ok": True, "params": normalized}
