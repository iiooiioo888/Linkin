"""應用層 Agent：靈境四部門席位分派草案。

不另開指揮鏈、不編譯第二套圖。草稿鍵對應既有子角色：
總監定界（system prompt）→ 執行者經 ``call_llm`` 產出 → 審查員用既有工具鐵律把關。
世界寫入仍走 ``/linkin/*`` 顯式 API；本模組只回傳草稿。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from backend.core.llm import call_llm
from backend.linkin.constitution import allowed_styles_for_region
from backend.linkin.narrative_commit import KNOWN_DRAFT_KEYS
from backend.linkin.narrative_starter import _extract_json_object
from backend.linkin.prompts import (
    ROLE_BUILD_DIRECTOR,
    ROLE_EXECUTOR,
    ROLE_ITEM_DIRECTOR,
    ROLE_NARRATIVE_DIRECTOR,
    ROLE_NPC_DIRECTOR,
    staff_prompt,
)
from backend.linkin.tools import (
    ToolValidationError,
    validate_builder_generate,
    validate_item_create,
    validate_no_command_chain,
    validate_npc_create,
    validate_quest_generate,
)

logger = logging.getLogger(__name__)

SCHEMA_HINTS: dict[str, str] = {
    "story_arc": "含 title, summary, region, chapters[](字串陣列), tags[]",
    "quest": "含 title, quest_type(主线/支线/日常), difficulty(简单/普通/困难), region, description, player_id",
    "npc": "含 name, faction, occupation, personality, backstory, location, speech_style",
    "item": "含 name, type(武器/防具/消耗品), rarity, attributes(物件), description",
    "build_brief": "含 title, region, location, style(區域允許風格), prompt, block_count(1–5000), notes",
}

SCHOOL_LABELS = {
    "narrative": "言靈",
    "npc": "共鳴",
    "item": "賦形",
    "build": "塑形",
}


class AppAgentError(ValueError):
    def __init__(self, message: str, *, code: str = "app_agent_failed", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail or message


@dataclass(frozen=True)
class AppSeat:
    department: str
    director_key: str
    executor_id: str
    reviewer_id: str
    keys: tuple[str, ...]

    @property
    def school(self) -> str:
        return SCHOOL_LABELS[self.department]


APPLICATION_SEATS: tuple[AppSeat, ...] = (
    AppSeat(
        "narrative",
        ROLE_NARRATIVE_DIRECTOR,
        "custom_linkin_narrative_executor",
        "custom_linkin_narrative_reviewer",
        ("story_arc", "quest"),
    ),
    AppSeat(
        "npc",
        ROLE_NPC_DIRECTOR,
        "custom_linkin_npc_executor",
        "custom_linkin_npc_reviewer",
        ("npc",),
    ),
    AppSeat(
        "item",
        ROLE_ITEM_DIRECTOR,
        "custom_linkin_item_executor",
        "custom_linkin_item_reviewer",
        ("item",),
    ),
    AppSeat(
        "build",
        ROLE_BUILD_DIRECTOR,
        "custom_linkin_build_executor",
        "custom_linkin_build_reviewer",
        ("build_brief",),
    ),
)


def seats_for_keys(keys: list[str]) -> list[AppSeat]:
    """依草稿鍵挑席。敘事席先跑，後續部門能對齊故事線。"""
    wanted = list(dict.fromkeys(keys))
    unknown = [key for key in wanted if key not in KNOWN_DRAFT_KEYS]
    if unknown:
        raise AppAgentError(f"未知草稿鍵：{', '.join(unknown)}", code="invalid_keys")
    wanted_set = set(wanted)
    selected: list[AppSeat] = []
    for seat in APPLICATION_SEATS:
        owned = tuple(key for key in seat.keys if key in wanted_set)
        if owned:
            selected.append(
                AppSeat(
                    seat.department,
                    seat.director_key,
                    seat.executor_id,
                    seat.reviewer_id,
                    owned,
                )
            )
    return selected


def review_draft(key: str, value: Any) -> dict[str, Any]:
    """審查員閘：沿用工具鐵律，不另叫一次模型。"""
    if not isinstance(value, dict):
        raise AppAgentError(f"「{key}」必須為 JSON 物件", code="invalid_schema")
    try:
        validate_no_command_chain(value)
    except ToolValidationError as exc:
        raise AppAgentError(str(exc), code="review_rejected", detail=exc.code) from exc

    if key == "story_arc":
        for field in ("title", "summary", "region"):
            if not str(value.get(field) or "").strip():
                raise AppAgentError(f"故事線缺少 {field}", code="review_rejected")
        chapters = value.get("chapters")
        if not isinstance(chapters, list) or not any(str(item).strip() for item in chapters):
            raise AppAgentError("故事線缺少 chapters", code="review_rejected")
        return dict(value)

    try:
        if key == "quest":
            if not str(value.get("title") or "").strip():
                raise AppAgentError("任務缺少 title", code="review_rejected")
            normalized = validate_quest_generate(value)
        elif key == "npc":
            normalized = validate_npc_create(value)
        elif key == "item":
            normalized = validate_item_create(value)
        elif key == "build_brief":
            if not str(value.get("title") or "").strip():
                raise AppAgentError("建築意圖缺少 title", code="review_rejected")
            normalized = validate_builder_generate(value)
        else:
            raise AppAgentError(f"未知草稿鍵：{key}", code="invalid_keys")
    except ToolValidationError as exc:
        raise AppAgentError(str(exc), code="review_rejected", detail=exc.code) from exc
    return {**value, **normalized}


def default_build_style(region: str) -> str:
    styles = allowed_styles_for_region(region) or []
    return styles[0] if styles else "契约广场"


def _system_for(seat: AppSeat) -> str:
    try:
        base = staff_prompt(seat.director_key, ROLE_EXECUTOR)
    except Exception:
        logger.warning("讀取 %s 席位提示詞失敗，改用部門特化", seat.executor_id, exc_info=True)
        from backend.linkin.prompts import specialization

        base = f"{specialization(seat.director_key)}\n\n{specialization(ROLE_EXECUTOR)}"
    return (
        f"{base}\n\n"
        f"你是應用層執行席 {seat.executor_id}（{seat.school}）。"
        "只輸出嚴格 JSON 物件，不要 markdown、不要解釋。"
        "禁止命令鏈，禁止改寫已記載歷史，禁止直寫世界。"
    )


def _prompt_for(
    seat: AppSeat,
    *,
    brief: str,
    locale: str,
    region: str,
    theme: str,
    prior: dict[str, Any],
) -> str:
    schema = "\n".join(f"- {key}: {SCHEMA_HINTS[key]}" for key in seat.keys)
    theme_line = f"主題提示：{theme}\n" if theme.strip() else ""
    prior_line = ""
    if prior:
        blob = json.dumps(prior, ensure_ascii=False)
        if len(blob) > 4000:
            blob = blob[:4000] + "…"
        prior_line = f"已定稿的其他部門草案（必須呼應，不得互相矛盾）：\n{blob}\n"
    return (
        f"為 Minecraft RPG 工作區產出本部門草稿。鍵必須恰好為：{', '.join(seat.keys)}。\n"
        f"{schema}\n"
        f"輸出語言：{locale}\n"
        f"區域：{region}\n"
        f"{theme_line}"
        f"{prior_line}"
        f"使用者 brief：\n{brief.strip()}\n"
    )


def _invoke_seat(
    seat: AppSeat,
    *,
    brief: str,
    locale: str,
    region: str,
    theme: str,
    prior: dict[str, Any],
) -> dict[str, Any]:
    prompt = _prompt_for(seat, brief=brief, locale=locale, region=region, theme=theme, prior=prior)
    try:
        raw = (
            call_llm(
                prompt,
                system=_system_for(seat),
                trace_label=f"app_agent:{seat.department}",
            )
            or ""
        ).strip()
    except AppAgentError:
        raise
    except Exception as exc:
        logger.warning("應用層席位 %s 呼叫失敗", seat.executor_id, exc_info=True)
        raise AppAgentError("LLM 呼叫失敗", code="llm_failed", detail=str(exc)) from exc

    parsed = _extract_json_object(raw)
    if not parsed:
        raise AppAgentError(
            f"{seat.school}席回傳無法解析為 JSON",
            code="parse_failed",
            detail=(raw[:500] if raw else ""),
        )
    missing = [key for key in seat.keys if key not in parsed]
    if missing:
        raise AppAgentError(
            f"{seat.school}席缺少草稿鍵：{', '.join(missing)}",
            code="missing_keys",
            detail=raw[:500],
        )
    return parsed


def dispatch_application_drafts(
    *,
    brief: str,
    keys: list[str],
    locale: str = "zh-Hant",
    region: str = "织庭都",
    theme: str = "",
) -> dict[str, Any]:
    """依部門席位產出並審查草稿。任一席失敗則整批不返回。"""
    text = (brief or "").strip()
    if not text:
        raise AppAgentError("需要 brief（主題／種子描述）", code="missing_brief")
    cleaned: list[str] = []
    for raw in keys:
        key = str(raw or "").strip()
        if key and key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        raise AppAgentError("需要至少一個草稿鍵", code="invalid_keys")
    keys = cleaned

    region = (region or "织庭都").strip() or "织庭都"
    locale = (locale or "zh-Hant").strip() or "zh-Hant"
    seats = seats_for_keys(keys)
    drafts: dict[str, Any] = {}
    agents: list[dict[str, Any]] = []
    for seat in seats:
        produced = _invoke_seat(
            seat,
            brief=text,
            locale=locale,
            region=region,
            theme=theme,
            prior=drafts,
        )
        for key in seat.keys:
            drafts[key] = review_draft(key, produced[key])
        agents.append(
            {
                "department": seat.department,
                "school": seat.school,
                "executor_id": seat.executor_id,
                "reviewer_id": seat.reviewer_id,
                "keys": list(seat.keys),
                "review": "pass",
            }
        )

    ordered = {key: drafts[key] for key in keys}
    return {"drafts": ordered, "agents": agents, "keys": list(keys)}


__all__ = [
    "APPLICATION_SEATS",
    "SCHEMA_HINTS",
    "AppAgentError",
    "AppSeat",
    "default_build_style",
    "dispatch_application_drafts",
    "review_draft",
    "seats_for_keys",
]
