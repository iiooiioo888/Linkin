"""任務目標模板：建立／提交任務時注入預設 objectives。"""

from __future__ import annotations

from typing import Any


def default_objectives_for_quest(
    *,
    title: str,
    description: str = "",
    quest_type: str = "支线",
) -> list[dict[str, Any]]:
    """依任務類型產生 2–3 個預設目標。"""
    title = (title or "任務").strip()
    desc = (description or "").strip()
    qtype = (quest_type or "支线").strip()
    objectives: list[dict[str, Any]] = [
        {"id": "obj-investigate", "title": f"調查：{title[:40]}", "description": desc[:120]},
    ]
    if qtype in {"主线", "支线"}:
        objectives.append(
            {"id": "obj-resolve", "title": "完成關鍵目標", "description": "依敘事線推進並回報結果"},
        )
    objectives.append(
        {"id": "obj-complete", "title": "交付任務", "description": "向相關 NPC 或系統確認完成"},
    )
    return objectives


def attach_objectives_if_missing(quest: dict[str, Any]) -> dict[str, Any]:
    """若 quest 無 objectives，注入預設模板（不覆寫既有）。"""
    if quest.get("objectives"):
        return quest
    quest = dict(quest)
    quest["objectives"] = default_objectives_for_quest(
        title=str(quest.get("title") or ""),
        description=str(quest.get("description") or ""),
        quest_type=str(quest.get("quest_type") or "支线"),
    )
    return quest


__all__ = ["attach_objectives_if_missing", "default_objectives_for_quest"]
