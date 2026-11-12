"""節點 5（自 backend.core.nodes 抽出）。

節點 5：最終回答決策與收尾（含交付端長度守門）。
"""

from __future__ import annotations

import logging
from typing import Any, Literal, cast

from backend.core.pipeline_trace import log_node
from backend.core.state import StateInput

from .length import enforce_final_length

logger = logging.getLogger(__name__)


def finalize_task_answer(state: StateInput) -> dict:
    """與 LangGraph 收尾一致：decide_final_answer → enforce_final_length。"""
    merged: dict[str, Any] = {}
    merged.update(decide_final_answer(state))
    interim = {**state, **merged}
    merged.update(enforce_final_length(interim))
    return merged


def decide_final_answer(state: StateInput) -> dict:
    """節點 5：決定最終回答並執行最終質量門檢查（優化 #16）。

    質量門：
    - 回答為空 → 使用初始回答降級
    - 回答過短（< 10 字）→ 標記警告
    - 回答與問題完全無關 → 標記警告
    """
    if state.get("length_refused"):
        return {
            "final_answer": "",
            "quality_warnings": ["長度不合規，已拒絕交付"],
            "length_warning": False,
        }

    answer = state.get("current_answer", "")
    query = state.get("query", "")
    warnings: list[str] = []

    # 質量門 1：空回答降級
    if not answer or not answer.strip():
        answer = state.get("initial_answer", "")
        if answer:
            warnings.append("current_answer 為空，降級使用 initial_answer")
        else:
            warnings.append("所有回答為空")
            answer = "抱歉，無法生成有效回答，請嘗試重新表述問題。"

    # 質量門 2：過短回答
    if len(answer.strip()) < 10:
        warnings.append(f"回答過短（{len(answer.strip())} 字）")

    # 質量門 3：相關性粗檢（查詢詞命中率）
    if query and len(query) > 5:
        query_chars = set(c for c in query if '\u4e00' <= c <= '\u9fff')
        answer_chars = set(c for c in answer if '\u4e00' <= c <= '\u9fff')
        if query_chars and answer_chars:
            overlap = len(query_chars & answer_chars) / len(query_chars)
            if overlap < 0.1:
                warnings.append(f"回答與問題關聯度極低（{overlap:.0%}）")

    if warnings:
        logger.warning("質量門警告：%s", "；".join(warnings))

    # P2：路由自適應反饋 — 記錄最終品質供後續調整
    try:
        from backend.core.routing_feedback import record_outcome

        exec_path = str(state.get("resolved_execution_path") or "").strip().lower()
        route = cast(
            Literal["simple", "company"],
            "company" if state.get("company_result") else "simple",
        )
        record_outcome(
            route=route,
            query_length=len(state.get("query", "")),
            score=float(state.get("score", 0.0)),
            success=not warnings and float(state.get("score", 0.0)) >= 8.0,
            execution_path=exec_path or None,
        )
        log_node(state, "decide_final_answer", route=route, score=state.get("score", 0.0))
    except Exception as exc:
        logger.debug("路由反饋記錄跳過：%s", exc)

    return {"final_answer": answer, "quality_warnings": warnings}
