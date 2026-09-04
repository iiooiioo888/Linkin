"""靈境子角色種子：建築／敘事／NPC／道具總監及其執行者、審查員、記錄員。"""

from __future__ import annotations

import logging
from typing import Any

from backend.company.role_catalog import create_custom_role, get_snapshot, update_role_settings
from backend.linkin.prompts import (
    ROLE_BUILD_DIRECTOR,
    ROLE_EXECUTOR,
    ROLE_ITEM_DIRECTOR,
    ROLE_NARRATIVE_DIRECTOR,
    ROLE_NPC_DIRECTOR,
    ROLE_REVIEWER,
    ROLE_SCRIBE,
    director_prompt,
    staff_prompt,
)

logger = logging.getLogger(__name__)

DEPARTMENTS: tuple[tuple[str, str, str, str], ...] = (
    (ROLE_BUILD_DIRECTOR, "build", "建築總監", "creative"),
    (ROLE_NARRATIVE_DIRECTOR, "narrative", "敘事總監", "creative"),
    (ROLE_NPC_DIRECTOR, "npc", "NPC總監", "creative"),
    (ROLE_ITEM_DIRECTOR, "item", "道具總監", "creative"),
)

STAFF: tuple[tuple[str, str, str, int, str], ...] = (
    (ROLE_EXECUTOR, "executor", "執行者", 2, "creative"),
    (ROLE_REVIEWER, "reviewer", "審查員", 3, "review"),
    (ROLE_SCRIBE, "scribe", "記錄員", 4, "memory"),
)


def _prompt_stale(text: str) -> bool:
    return "待Phase" in text or "需在Phase 1" in text or "[待补充]" in text or "[待補充]" in text


def _safe_create(payload: dict[str, Any]) -> dict[str, Any] | None:
    slug = payload["id"]
    prefixed = slug if slug.startswith("custom_") else f"custom_{slug}"
    existing = get_snapshot(prefixed)
    new_prompt = str(payload.get("system_prompt") or "")
    if existing is not None:
        old_prompt = str(existing.get("system_prompt") or "")
        if new_prompt and (old_prompt != new_prompt or _prompt_stale(old_prompt)):
            try:
                return update_role_settings(prefixed, {"system_prompt": new_prompt})
            except Exception as exc:  # noqa: BLE001
                logger.warning("刷新靈境角色提示詞失敗 %s：%s", prefixed, exc)
                return existing
        return existing
    try:
        return create_custom_role(payload)
    except ValueError as exc:
        if "已存在" in str(exc):
            return get_snapshot(prefixed)
        logger.warning("建立靈境角色失敗 %s：%s", slug, exc)
        return None


def seed_linkin_roles() -> list[dict[str, Any]]:
    """冪等寫入 16 個 Linkin 子角色（4 總監 × 總監+執行者+審查員+記錄員）。"""
    created: list[dict[str, Any]] = []
    for spec_key, slug, title, category in DEPARTMENTS:
        director_id = f"linkin_{slug}_director"
        director = _safe_create(
            {
                "id": director_id,
                "name": title,
                "level": 1,
                "category": category,
                "reporting_to": None,
                "responsibilities": [
                    f"作為靈境·Linkin {title}，分解部門任務並指派執行者",
                    "在工具鐵律下完成合規檢查",
                    "衝突時以世界觀憲法為最高裁決依據",
                ],
                "system_prompt": director_prompt(spec_key),
                "default_tier": "reasoning",
                "max_parallel_work": 4,
                "tags": ["linkin", slug, "director"],
                "notes": "靈境·Linkin L1 部門主管，system_prompt 繼承頂層提示詞。",
            }
        )
        if director is None:
            logger.warning("靈境總監建立失敗，跳過該部門職員角色：%s", director_id)
            continue
        created.append(director)
        director_catalog_id = str(director.get("id") or f"custom_{director_id}")
        for staff_key, staff_slug, staff_title, level, staff_cat in STAFF:
            role = _safe_create(
                {
                    "id": f"linkin_{slug}_{staff_slug}",
                    "name": f"{title.replace('總監', '')}{staff_title}",
                    "level": level,
                    "category": staff_cat,
                    "reporting_to": director_catalog_id,
                    "responsibilities": [
                        f"在{title}指導下擔任{staff_title}",
                        "遵守單次一工具、禁止命令鏈、敏感操作二次確認",
                    ],
                    "system_prompt": staff_prompt(spec_key, staff_key),
                    "default_tier": "routine" if level >= 3 else "reasoning",
                    "max_parallel_work": 2,
                    "tags": ["linkin", slug, staff_slug],
                    "notes": f"靈境·Linkin L{level} {staff_title}，繼承頂層提示詞。",
                }
            )
            if role:
                created.append(role)
    return created
