"""靈境子角色種子：建築／敘事／NPC／道具總監及其執行者、審查員、記錄員。"""

from __future__ import annotations

import logging
from typing import Any

from backend.company.role_catalog import (
    backfill_custom_role_budgets,
    create_custom_role,
    get_snapshot,
    update_role_settings,
)
from backend.linkin.budget_defaults import budgets_for_role, is_linkin_role
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

MC_READ_TOOLS = ["get_player", "get_online_players"]
MC_BUILD_TOOLS = ["place_block", "break_block", "fill_block", "pose_block", *MC_READ_TOOLS]
MC_ADMIN_TOOLS = [*MC_BUILD_TOOLS, "execute_command"]
DOMAIN_TOOLS = {
    "build": ["BuilderAI.generate"],
    "narrative": ["Quest.generate"],
    "npc": ["NPC.create", "NPC.dialogue"],
    "item": ["Item.create"],
}


def _tools_for(dept_slug: str, staff_slug: str | None) -> list[str]:
    domain = list(DOMAIN_TOOLS.get(dept_slug, []))
    if staff_slug in {ROLE_REVIEWER, ROLE_SCRIBE}:
        return list(MC_READ_TOOLS)
    if dept_slug == "build":
        if staff_slug is None:
            return [*domain, *MC_ADMIN_TOOLS]
        if staff_slug == ROLE_EXECUTOR:
            return [*domain, *MC_BUILD_TOOLS]
        return list(MC_READ_TOOLS)
    if dept_slug in {"narrative", "npc", "item"}:
        if staff_slug == ROLE_EXECUTOR:
            return [*domain, *MC_READ_TOOLS]
        return list(MC_READ_TOOLS)
    return []

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

# 部門特化元資料：學派、職責、溫度、優先級（名稱保持 建築執行者／敘事審查員 等既有慣例）
DEPT_META: dict[str, dict[str, Any]] = {
    "build": {
        "school": "塑形學派",
        "director_focus": "風格與區域文化匹配、單次 ≤5000 方塊預算、靈脈和諧否決權",
        "executor_duty": "用 place_block／fill_block／break_block 落地建築方案並附自檢清單",
    },
    "narrative": {
        "school": "言靈學派",
        "director_focus": "三大陣營張力為唯一衝突源泉、重大歷史不可改寫",
        "executor_duty": "產出任務大綱與事件年表條目，Quest.generate 僅限 主線／支線／日常",
    },
    "npc": {
        "school": "共鳴學派",
        "director_focus": "角色卡四要素（背景／性格／陣營／語言）不可衝突、無直寫 RAG 權",
        "executor_duty": "產出角色卡與對話樣例，對話前必檢 linkin_npcs（閾值 0.75）",
    },
    "item": {
        "school": "賦形學派",
        "director_focus": "稀有度平衡區間否決權、生成前必檢道具庫防換皮",
        "executor_duty": "產出道具卡與平衡說明，Item.create 僅限 武器／防具／消耗品",
    },
}

# 崗位運行參數：越接近裁決與寫入，越要確定性（低溫）與低併發
STAFF_RUNTIME: dict[str, dict[str, Any]] = {
    ROLE_EXECUTOR: {"temperature": 0.7, "priority": 3, "max_parallel_work": 3},
    ROLE_REVIEWER: {"temperature": 0.2, "priority": 4, "max_parallel_work": 2,
                    "always_require_review": False},
    ROLE_SCRIBE: {"temperature": 0.3, "priority": 2, "max_parallel_work": 1},
}
DIRECTOR_RUNTIME: dict[str, Any] = {
    "temperature": 0.5,
    "priority": 4,
    "max_parallel_work": 4,
    "auto_escalate": True,
}


def _prompt_stale(text: str) -> bool:
    return "待Phase" in text or "需在Phase 1" in text or "[待补充]" in text or "[待補充]" in text


# 重灌時需要全量對齊的字段（提示詞之外，結構／數據也隨代碼演進刷新）
_SYNC_FIELDS = (
    "name",
    "level",
    "category",
    "reporting_to",
    "can_delegate_to",
    "responsibilities",
    "system_prompt",
    "max_parallel_work",
    "default_tier",
    "description",
    "notes",
    "temperature",
    "priority",
    "tags",
    "always_require_review",
    "auto_escalate",
    "tools_allowed",
    "allow_tool_use",
)


def _safe_create(payload: dict[str, Any]) -> dict[str, Any] | None:
    slug = payload["id"]
    prefixed = slug if slug.startswith("custom_") else f"custom_{slug}"
    existing = get_snapshot(prefixed)
    if existing is not None:
        patch: dict[str, Any] = {}
        old_prompt = str(existing.get("system_prompt") or "")
        new_prompt = str(payload.get("system_prompt") or "")
        prompt_drift = new_prompt and (old_prompt != new_prompt or _prompt_stale(old_prompt))
        for field in _SYNC_FIELDS:
            if field == "system_prompt":
                continue
            wanted = payload.get(field)
            if wanted is None:
                continue
            current = existing.get(field)
            if field == "reporting_to" and not wanted:
                continue
            if current != wanted:
                patch[field] = wanted
        if prompt_drift:
            patch["system_prompt"] = new_prompt
        if patch:
            try:
                return update_role_settings(prefixed, patch)
            except Exception as exc:
                logger.warning("刷新靈境角色設定失敗 %s：%s", prefixed, exc)
                return existing
        return existing
    try:
        return create_custom_role(payload)
    except ValueError as exc:
        if "已存在" in str(exc):
            return get_snapshot(prefixed)
        logger.warning("建立靈境角色失敗 %s：%s", slug, exc)
        return None


def backfill_linkin_role_budgets() -> int:
    """為尚未自訂預算的靈境子角色回填預設 AI／雲預算。不回寫已設正值或 settings 覆蓋。"""
    from backend.company.role_catalog import _load_store, reset_catalog_cache

    store = _load_store()
    count = 0
    for raw in store.get("custom") or []:
        if not isinstance(raw, dict) or not is_linkin_role(raw):
            continue
        role_id = str(raw.get("id") or "")
        if not role_id:
            continue
        if backfill_custom_role_budgets(role_id, budgets_for_role(role_id)):
            count += 1
    reset_catalog_cache()
    return count


def seed_linkin_roles() -> list[dict[str, Any]]:
    """冪等寫入 16 個 Linkin 子角色（4 總監 × 總監+執行者+審查員+記錄員）。

    v2.0：除提示詞外，同步刷新名稱／職責／層級／委派鏈／運行參數，
    讓監控中心與代碼定義不再漂移。
    """
    created: list[dict[str, Any]] = []
    for spec_key, slug, title, category in DEPARTMENTS:
        meta = DEPT_META[slug]
        director_id = f"linkin_{slug}_director"
        director_staff_ids = [f"custom_linkin_{slug}_{s}" for _, s, _, _, _ in STAFF]
        director = _safe_create(
            {
                "id": director_id,
                "name": title,
                "level": 1,
                "category": category,
                "reporting_to": None,
                "can_delegate_to": director_staff_ids,
                "responsibilities": [
                    f"作為靈境·Linkin {title}（{meta['school']}負責人），分解部門任務並委派給本部門執行者",
                    f"域內把關：{meta['director_focus']}",
                    "在工具鐵律下完成合規檢查：單次一工具、禁命令鏈、敏感操作二次確認",
                    "衝突時以世界觀憲法為最高裁決依據；跨部門分歧上報核心意志（Level 0）",
                ],
                "system_prompt": director_prompt(spec_key),
                "default_tier": "reasoning",
                "description": f"靈境四部門之一 · {meta['school']} L1 主管",
                "notes": "靈境·Linkin L1 部門主管，system_prompt = 頂層提示詞 v2.0 + 崗位特化。",
                "tags": ["linkin", slug, "director"],
                "tools_allowed": _tools_for(slug, None),
                "allow_tool_use": True,
                **DIRECTOR_RUNTIME,
                **budgets_for_role(director_id),
            }
        )
        if director is None:
            logger.warning("靈境總監建立失敗，跳過該部門職員角色：%s", director_id)
            continue
        created.append(director)
        director_catalog_id = str(director.get("id") or f"custom_{director_id}")
        for staff_key, staff_slug, staff_title, level, staff_cat in STAFF:
            staff_runtime = STAFF_RUNTIME.get(staff_key, {})
            staff_title_full = f"{title.replace('總監', '')}{staff_title}"
            staff_duty = {
                ROLE_EXECUTOR: meta["executor_duty"],
                ROLE_REVIEWER: "四維度評分（準確性／完整性／清晰度／相關性），百分制 ≥80 放行，否則退回並給改進方案",
                ROLE_SCRIBE: "僅寫入審查通過的產出到 RAG 四庫；Chroma 不可用降級 JSON 並標註 backend=json",
            }[staff_key]
            role = _safe_create(
                {
                    "id": f"linkin_{slug}_{staff_slug}",
                    "name": staff_title_full,
                    "level": level,
                    "category": staff_cat,
                    "reporting_to": director_catalog_id,
                    "can_delegate_to": [],
                    "responsibilities": [
                        f"在{title}指導下擔任{staff_title}：{staff_duty}",
                        "遵守單次一工具、禁止命令鏈、敏感操作二次確認",
                        "產出與失敗原因全程留痕，供執行軌跡與監控中心複核",
                    ],
                    "system_prompt": staff_prompt(spec_key, staff_key),
                    "default_tier": "routine" if level >= 3 else "reasoning",
                    "description": f"{meta['school']}流水線 L{level} · {staff_title}",
                    "notes": f"靈境·Linkin L{level} {staff_title}，system_prompt = 頂層提示詞 v2.0 + 總監特化 + 崗位特化。",
                    "max_parallel_work": 2,
                    "tags": ["linkin", slug, staff_slug],
                    "tools_allowed": _tools_for(slug, staff_key),
                    "allow_tool_use": True,
                    **staff_runtime,
                    **budgets_for_role(f"linkin_{slug}_{staff_slug}"),
                }
            )
            if role:
                created.append(role)
    backfill_linkin_role_budgets()
    return created
