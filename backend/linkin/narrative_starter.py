"""Phase 0 一鍵草案：LLM 或本地模板填充 story_arc／quest／npc／item／build_brief。

不自動 commit；由使用者在前端按「提交至 Linkin」。
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_ready() -> bool:
    if os.getenv("EVOL_LINKIN_NO_LLM", "").strip().lower() in {"1", "true", "yes"}:
        return False
    try:
        from backend.core.llm_config import get_runtime_config

        cfg = get_runtime_config()
        key = str(cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    except Exception:
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")


def fallback_starter_pack(*, region: str = "织庭都", theme: str = "靈丝残章") -> dict[str, Any]:
    """無 LLM 時的確定性草案包。風格與屬性落在憲法允許區間。"""
    from backend.linkin.app_agents import default_build_style

    style = default_build_style(region)
    return {
        "story_arc": {
            "title": theme,
            "summary": f"旅人在{region}發現與「{theme}」相關的異象，需串連 NPC、任務與建築意圖推進主線。",
            "region": region,
            "chapters": ["序章：抵達與異象", "第一章：追尋殘章", "第二章：契約與抉擇"],
            "tags": ["主線", region],
        },
        "quest": {
            "title": f"支線：{theme}",
            "quest_type": "支线",
            "difficulty": "普通",
            "region": region,
            "description": f"在{region}調查與「{theme}」相關的線索，並向關鍵 NPC 回報。",
            "player_id": "traveler-01",
        },
        "npc": {
            "name": "草案·青禾",
            "faction": "织庭盟",
            "occupation": "典章抄錄者",
            "personality": "沉靜、記性極佳、以故事串連記憶",
            "backstory": (
                f"青禾長駐{region}，專門記錄旅人口述的片段傳說。"
                f"她相信每一段未完成的對話都會在「{theme}」中開花。"
            ),
            "location": region,
            "speech_style": "白描敘事",
        },
        "item": {
            "name": "靈丝殘章",
            "type": "消耗品",
            "rarity": "common",
            "attributes": {"power": 8},
            "description": f"與「{theme}」共鳴的碎片，可觸發後續任務線。",
        },
        "build_brief": {
            "title": f"{region}序章廣場",
            "region": region,
            "location": "0,64,0",
            "style": style,
            "prompt": f"帶金線紋樣的開場廣場，中央有契約碑，呼應「{theme}」。",
            "block_count": 800,
            "notes": "Phase 0 僅落庫意圖；MineMCP 建造見 Phase 2。",
        },
    }


def generate_starter_pack(*, region: str = "织庭都", theme: str = "靈丝残章") -> dict[str, Any]:
    """嘗試 LLM 生成草案包；失敗則回退 fallback_starter_pack。"""
    region = (region or "织庭都").strip() or "织庭都"
    theme = (theme or "靈丝残章").strip() or "靈丝残章"
    if not _llm_ready():
        return {"drafts": fallback_starter_pack(region=region, theme=theme), "source": "fallback"}

    try:
        from backend.linkin.app_agents import dispatch_application_drafts

        dispatched = dispatch_application_drafts(
            brief=f"區域 {region}，主題 {theme}",
            keys=["story_arc", "quest", "npc", "item", "build_brief"],
            region=region,
            theme=theme,
        )
        return {"drafts": dispatched["drafts"], "source": "llm", "agents": dispatched["agents"]}
    except Exception:
        logger.warning("一鍵草案應用席失敗，改用本地模板", exc_info=True)

    return {"drafts": fallback_starter_pack(region=region, theme=theme), "source": "fallback"}


__all__ = ["fallback_starter_pack", "generate_starter_pack"]
