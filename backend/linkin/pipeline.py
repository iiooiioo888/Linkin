"""靈境上下文增強：掛在統一管線上，對齊 OPC 的「感知後注入」模式。

非靈境查詢一律空物件返回，不碰 RAG、不改路由。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.core.state import EvoLoopState

logger = logging.getLogger(__name__)

_LINKIN_WORLD_RE = re.compile(
    r"("
    r"灵境|靈境|linkin|"
    r"织庭|織庭|自由舟|宁渊|寧淵|"
    r"灵丝|靈絲|织梦者|織夢者|"
    r"精灵森林|精靈森林|裂隙港|织庭都|織庭都|宁渊谷|寧淵谷|"
    r"aetherthread|will of linkin"
    r")",
    re.IGNORECASE,
)

_LINKIN_WORK_RE = re.compile(
    r"("
    r"建造|建筑|建築|扩建|擴建|改建|主城|"
    r"NPC|角色卡|"
    r"任务|任務|主线|主線|支线|支線|"
    r"道具|附魔|"
    r"世界观|世界觀|宪法|憲法|"
    r"BuilderAI"
    r")",
    re.IGNORECASE,
)

_SYSTEM_OVERLAY = (
    "你正在協助「靈境·Linkin」。必須遵守世界觀憲法："
    "三大陣營（織庭盟／自由舟／寧淵庭）張力為故事源泉；"
    "魔法僅能以靈絲術解釋；禁止現實政治、宗教、色情與寫實暴力；"
    "不得改寫已記載歷史；建築風格須匹配區域；NPC 背景不可為空。"
)


def needs_linkin_context(query: str) -> bool:
    """查詢是否涉及靈境世界觀（僅注入 RAG，不強制公司運行時）。"""
    return bool(_LINKIN_WORLD_RE.search(query or ""))


def is_linkin_complex_task(query: str) -> bool:
    """靈境世界觀 + 建造／NPC／任務／道具等工作動詞 → 走公司運行時。"""
    text = query or ""
    return bool(_LINKIN_WORLD_RE.search(text) and _LINKIN_WORK_RE.search(text))


def constitution_brief() -> str:
    """壓縮憲法摘要，供 prompt 注入。失敗時靜默降級。"""
    try:
        from backend.linkin.constitution import load_constitution

        const = load_constitution()
    except Exception as exc:  # noqa: BLE001
        logger.warning("讀取靈境憲法失敗（跳過注入）：%s", exc)
        return ""
    foundation = const.get("foundation") or {}
    factions = "、".join(
        str(f.get("name") or "") for f in (const.get("factions") or []) if f.get("name")
    )
    magic = (const.get("magic") or {}).get("name") or "灵丝术"
    conflict = str(foundation.get("core_conflict") or "")[:240]
    return (
        "【靈境世界觀憲法】\n"
        f"世界：{const.get('world_name') or '灵境·Linkin'}。"
        f"造物主：{foundation.get('creator') or '织梦者'}。"
        f"核心衝突：{conflict}\n"
        f"陣營：{factions or '织庭盟、自由舟、宁渊庭'}。魔法：{magic}。\n"
        "邊界：禁止現實政治／宗教／色情／寫實暴力；NPC 背景不可為空；"
        "建築風格須匹配區域；歷史不可矛盾。"
    )


def enhance_with_linkin_context(state: EvoLoopState) -> dict[str, Any]:
    """靈境 RAG 增強：命中世界觀關鍵詞時注入憲法摘要與知識庫檢索。

    知識庫／憲法不可用時靜默降級（不中斷主流程）。
    """
    query = state.get("query", "")
    if not needs_linkin_context(query):
        return {"linkin_context": {}}

    brief = constitution_brief()
    hits: list[dict[str, Any]] = []
    backend = "none"
    try:
        from backend.linkin.knowledge import COL_WORLDVIEW, COL_NPCS, COL_EVENTS, get_store

        store = get_store()
        backend = "chroma" if store.backend_status().get("chroma") else "json"
        for collection in (COL_WORLDVIEW, COL_NPCS, COL_EVENTS):
            hits.extend(store.search(collection, query, k=2))
    except Exception as exc:  # noqa: BLE001
        logger.warning("靈境 RAG 檢索失敗（降級僅憲法）：%s", exc)

    hit_lines: list[str] = []
    for hit in hits[:6]:
        text = str(hit.get("text") or "").replace("\n", " ").strip()
        if text:
            hit_lines.append(f"- {text[:160]}")
    rag_block = ("\n【靈境知識庫】\n" + "\n".join(hit_lines)) if hit_lines else ""
    summary = f"{brief}{rag_block}".strip()
    return {
        "linkin_context": {
            "active": True,
            "summary": summary,
            "system_overlay": _SYSTEM_OVERLAY,
            "complex": is_linkin_complex_task(query),
            "rag_hits": len(hits),
            "backend": backend,
        }
    }


def resolve_linkin_company_template(state: EvoLoopState) -> str | None:
    """靈境複雜任務且呼叫端仍用預設 quick_task 時，改走故事工作室。"""
    ctx = state.get("linkin_context") or {}
    if not isinstance(ctx, dict) or not ctx.get("active"):
        return None
    if not ctx.get("complex") and not is_linkin_complex_task(state.get("query", "")):
        return None
    current = str(state.get("company_template") or "quick_task").strip() or "quick_task"
    if current == "quick_task":
        return "story_studio"
    return None


def prefix_query_with_linkin(query: str, state: EvoLoopState) -> str:
    ctx = state.get("linkin_context") or {}
    if not isinstance(ctx, dict):
        return query
    summary = str(ctx.get("summary") or "").strip()
    if not summary:
        return query
    return f"{summary}\n\n【使用者目標】\n{query}"
