"""Phase 1 敘事草案 AI 一鍵生成：依使用者 brief 填充草稿鍵，不 commit。

寫入策略：成功時以 **replace-per-key** 覆寫所請求的草稿鍵；解析失敗時不修改任何既有草稿。
計量：經 ``backend.core.llm.call_llm``（與其他 Linkin 生成路徑相同）。
"""

from __future__ import annotations

import logging
from typing import Any

from backend.linkin.narrative_commit import KNOWN_DRAFT_KEYS
from backend.linkin.narrative_starter import _extract_json_object, _llm_ready

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "zh-Hant"
TRACE_LABEL = "narrative_generate"

_KEY_SCHEMA_HINTS: dict[str, str] = {
    "story_arc": "含 title, summary, region, chapters[](字串陣列), tags[]",
    "quest": "含 title, quest_type, difficulty, region, description, player_id",
    "npc": "含 name, faction, occupation, personality, backstory, location, speech_style",
    "item": "含 name, type(武器/防具/消耗品), rarity(common/uncommon/rare), attributes(物件), description",
    "build_brief": "含 title, region, location, style, prompt, block_count(整數), notes",
}


class NarrativeGenerateError(ValueError):
    def __init__(self, message: str, *, code: str = "generate_failed", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail or message


def _normalize_keys(keys: list[str] | None) -> list[str]:
    if not keys:
        return sorted(KNOWN_DRAFT_KEYS)
    normalized: list[str] = []
    for raw in keys:
        key = str(raw or "").strip()
        if not key:
            continue
        if key not in KNOWN_DRAFT_KEYS:
            raise NarrativeGenerateError(f"未知草稿鍵：{key}", code="invalid_keys")
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise NarrativeGenerateError("需要至少一個草稿鍵", code="invalid_keys")
    return normalized


def _build_prompt(
    *,
    brief: str,
    locale: str,
    keys: list[str],
    region: str,
    theme: str,
) -> str:
    schema_lines = "\n".join(f"- {key}: {_KEY_SCHEMA_HINTS[key]}" for key in keys)
    theme_line = f"主題提示：{theme}\n" if theme.strip() else ""
    return (
        "為 Minecraft RPG 敘事工作區生成一組互相連結的草案。只輸出 JSON 物件，"
        f"鍵必須恰好為：{', '.join(keys)}。\n"
        f"{schema_lines}\n"
        "各草案內容須彼此呼應（同一故事線、任務與 NPC、道具、建築意圖一致）。\n"
        f"輸出語言：{locale}\n"
        f"區域：{region}\n"
        f"{theme_line}"
        f"使用者 brief：\n{brief.strip()}\n"
    )


def _validate_draft_value(key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NarrativeGenerateError(
            f"LLM 回傳的「{key}」必須為 JSON 物件",
            code="invalid_schema",
        )
    return dict(value)


def generate_narrative_drafts(
    *,
    brief: str,
    locale: str = DEFAULT_LOCALE,
    keys: list[str] | None = None,
    region: str = "织庭都",
    theme: str = "",
) -> dict[str, Any]:
    """依 brief 呼叫 LLM 生成所請求草稿鍵。成功回傳 ``{drafts, source}``。"""
    text = (brief or "").strip()
    if not text:
        raise NarrativeGenerateError("需要 brief（主題／種子描述）", code="missing_brief")

    target_keys = _normalize_keys(keys)
    region = (region or "织庭都").strip() or "织庭都"
    locale = (locale or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE

    if not _llm_ready():
        raise NarrativeGenerateError(
            "LLM 未配置（請設定 API 金鑰或關閉 EVOL_LINKIN_NO_LLM）",
            code="llm_unavailable",
        )

    try:
        from backend.core.llm import call_llm

        try:
            from backend.linkin.prompts import inherit_prompt

            system = inherit_prompt("narrative_director")
        except Exception:
            system = "你是靈境·Linkin 敘事總監。輸出須符合世界觀憲法，禁止現實政治與寫實暴力。"
        system = (
            f"{system}\n"
            "你只輸出嚴格 JSON 物件，不要 markdown 程式碼區塊、不要解釋文字。"
        )
        prompt = _build_prompt(
            brief=text,
            locale=locale,
            keys=target_keys,
            region=region,
            theme=theme,
        )
        raw = (call_llm(prompt, system=system, trace_label=TRACE_LABEL) or "").strip()
    except NarrativeGenerateError:
        raise
    except Exception as exc:
        logger.warning("敘事草案 LLM 呼叫失敗", exc_info=True)
        raise NarrativeGenerateError(
            "LLM 呼叫失敗",
            code="llm_failed",
            detail=str(exc),
        ) from exc

    parsed = _extract_json_object(raw)
    if not parsed:
        raise NarrativeGenerateError(
            "LLM 回傳無法解析為 JSON",
            code="parse_failed",
            detail=(raw[:500] if raw else ""),
        )

    missing = [key for key in target_keys if key not in parsed]
    if missing:
        raise NarrativeGenerateError(
            f"LLM 回傳缺少草稿鍵：{', '.join(missing)}",
            code="missing_keys",
            detail=raw[:500],
        )

    drafts: dict[str, Any] = {}
    for key in target_keys:
        drafts[key] = _validate_draft_value(key, parsed[key])

    return {"drafts": drafts, "source": "llm", "keys": target_keys}


__all__ = [
    "DEFAULT_LOCALE",
    "NarrativeGenerateError",
    "generate_narrative_drafts",
]
