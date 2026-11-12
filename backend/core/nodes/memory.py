"""向量記憶體代理、對話歷史／記憶格式化、檢索與保存。（自 backend.core.nodes 抽出）。

向量記憶體代理、對話歷史／記憶格式化、檢索與保存。
"""

from __future__ import annotations

import logging

from backend.core.state import StateInput

from ._compat import get_memory_store as _get_memory_store

logger = logging.getLogger(__name__)


# Phase 2：使用 ChromaDB 向量記憶庫。已登入時轉到該帳號的 collection。
class _TenantMemoryProxy:
    """屬性轉發到目前租戶的記憶庫；測試可整顆 patch 掉。"""

    def __getattr__(self, name: str):
        from backend.memory.tenant_store import vector_store_for_request

        return getattr(vector_store_for_request(), name)


_memory_store = _TenantMemoryProxy()


def _compress_history_turn(content: str, max_chars: int = 80) -> str:
    """將較早的對話輪次壓縮為一行摘要。"""
    text = (content or "").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _format_history(history: list[dict[str, str]]) -> str:
    """將多輪對話歷史格式化為 Prompt 區塊（含壓縮機制）。

    - 超過 6 輪或總字數 > 3000 時，較早輪次壓縮為摘要行
    - 最近 4 輪保留完整內容
    """
    if not history:
        return ""
    total_chars = sum(len(t.get("content", "")) for t in history)
    need_compress = len(history) > 6 or total_chars > 3000

    lines = ["【對話歷史】"]
    if need_compress and len(history) > 4:
        older = history[:-4]
        for turn in older:
            role = "使用者" if turn.get("role") == "user" else "助手"
            lines.append(f"{role}（摘要）：{_compress_history_turn(turn.get('content', ''))}")
        recent = history[-4:]
    else:
        recent = history[-6:]

    for turn in recent:
        role = "使用者" if turn.get("role") == "user" else "助手"
        lines.append(f"{role}：{turn.get('content', '')}")
    return "\n".join(lines) + "\n"


def _format_memories(memories: list[str]) -> str:
    """將檢索到的相似經驗格式化為 few-shot 參考區塊。"""
    if not memories:
        return ""
    lines = ["【可參考的過往成功經驗】"]
    for i, memory in enumerate(memories, 1):
        lines.append(f"{i}. {memory}")
    return "\n".join(lines) + "\n"


def retrieve_memories(state: StateInput) -> dict:
    """節點 0：從向量記憶庫檢索與查詢相似的成功經驗。

    在生成回答前執行，將檢索結果注入 state 供
    generate_initial_answer 作為 few-shot 參考。
    """
    query = state.get("query", "")
    if not query:
        return {"retrieved_memories": []}
    complexity = ""
    try:
        from backend.core.cost_speed_router import classify_task_complexity

        complexity = classify_task_complexity(query)
    except Exception:
        complexity = ""

    try:
        results = _get_memory_store().search_similar(query, k=3)
        memories = [item["text"] for item in results]
        payload: dict = {"retrieved_memories": memories}
        if complexity:
            payload["task_complexity"] = complexity
        return payload
    except Exception as exc:
        logger.warning("記憶檢索失敗（跳過）：%s", exc)
        payload = {"retrieved_memories": []}
        if complexity:
            payload["task_complexity"] = complexity
        return payload


def _search_reflection_hints(query: str) -> str:
    """從向量記憶庫檢索相似問題的歷史反思，供復用。"""
    if not query:
        return ""
    try:
        results = _get_memory_store().search_similar(query, k=2)
        hints: list[str] = []
        for item in results:
            meta = item.get("metadata") or {}
            if meta.get("type") != "reflection":
                continue
            text = item.get("text", "")
            if "反思：" in text:
                hints.append(text.split("反思：", 1)[1].split("\n", 1)[0][:300])
        if hints:
            return "【可參考的歷史反思】\n" + "\n".join(f"- {h}" for h in hints) + "\n"
    except Exception as exc:
        logger.debug("反思復用檢索跳過：%s", exc)
    return ""


def save_memory(state: StateInput) -> dict:
    """節點 6：將經驗嵌入並存入向量記憶庫（優化 #5）。

    保存策略：
    - 經歷反思改進並通過的案例 → 保存反思過程（學習價值高）
    - 一次通過的高分回答（score >= 8）→ 也保存為正樣本
    - 低分一次通過的回答 → 不保存（噪音）
    """
    score = state.get("score", 0.0)
    reflections = state.get("reflections", [])

    if reflections:
        # 經歷反思改進的案例
        last = reflections[-1]
        text = (
            f"問題：{state['query']}\n"
            f"反思：{last['critique']}\n"
            f"最終答案：{state.get('final_answer', '')}"
        )
        metadata = {
            "score": score,
            "iterations": state.get("iteration", 0),
            "type": "reflection",
        }
    elif score >= 8.0:
        # 一次通過的高分回答 → 保存為正樣本
        text = (
            f"問題：{state['query']}\n"
            f"高分回答：{state.get('final_answer', '')}"
        )
        metadata = {
            "score": score,
            "iterations": 0,
            "type": "positive_sample",
        }
    else:
        return {"memory_saved": False}

    try:
        _get_memory_store().add_memory(text, metadata=metadata)
        return {"memory_saved": True}
    except Exception as exc:
        logger.warning("記憶儲存失敗：%s", exc)
        return {"memory_saved": False}
