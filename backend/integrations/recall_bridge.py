"""整合召回橋接：主聊天路徑與 ``POST /integrations/recall`` 共用。

在每次使用者對話輪次、主 LLM 生成前呼叫 ``ContextAssembler``，
將 MemOS / OpenViking / WeKnora 片段 fail-open 注入 prompt。
客戶端建構與 integrations API registry 一致（``get_registry``）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.core.state import StateInput
from backend.integrations.context_assembler import AssembledContext, ContextAssembler, RecallPolicy
from backend.integrations.weknora import default_knowledge_base_id

logger = logging.getLogger(__name__)


def default_cube_ids(env: dict[str, str] | None = None) -> list[str]:
    """MemOS 召回 cube 列表（``LINKIN_MEMOS_CUBE_IDS``，逗號分隔）。"""
    e = env if env is not None else os.environ
    raw = e.get("LINKIN_MEMOS_CUBE_IDS", "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def default_recall_user_id(state: StateInput | None = None, env: dict[str, str] | None = None) -> str:
    """召回使用者 id：state → env ``LINKIN_RECALL_USER_ID`` → session_id → default。"""
    if state:
        explicit = state.get("user_id") or state.get("recall_user_id")
        if explicit:
            return str(explicit)
        session_id = state.get("session_id")
        if session_id:
            return str(session_id)
    e = env if env is not None else os.environ
    from_env = e.get("LINKIN_RECALL_USER_ID", "").strip()
    if from_env:
        return from_env
    return "default"


def resolve_recall_params(state: StateInput) -> dict[str, Any]:
    """從 state 與環境變數解析 assembler 參數。"""
    cube_ids = state.get("cube_ids") or state.get("memos_cube_ids")
    if not cube_ids:
        cube_ids = default_cube_ids()
    elif isinstance(cube_ids, str):
        cube_ids = [p.strip() for p in cube_ids.split(",") if p.strip()]

    kb_id = str(state.get("knowledge_base_id") or state.get("weknora_kb_id") or default_knowledge_base_id())
    return {
        "user_id": default_recall_user_id(state),
        "cube_ids": list(cube_ids),
        "knowledge_base_id": kb_id,
    }


def build_recall_assembler(*, policy: RecallPolicy | None = None) -> ContextAssembler:
    """以 integrations registry 建立召回編排器（與 API 一致）。"""
    from backend.integrations.api import get_registry

    reg = get_registry()
    return ContextAssembler(
        memos=reg["memos"],
        viking=reg["openviking"],
        weknora=reg["weknora"],
        policy=policy or RecallPolicy(),
    )


def assemble_recall_context(
    query: str,
    history: list[dict[str, str]] | None = None,
    *,
    user_id: str = "default",
    cube_ids: list[str] | None = None,
    knowledge_base_id: str = "",
    audit_path: bool = False,
    assembler: ContextAssembler | None = None,
) -> AssembledContext:
    """執行召回編排；外層異常由呼叫方 fail-open 處理。"""
    asm = assembler or build_recall_assembler()
    return asm.assemble(
        query,
        history or [],
        user_id=user_id,
        cube_ids=cube_ids or [],
        knowledge_base_id=knowledge_base_id,
        audit_path=audit_path,
    )


def assembled_to_state_update(assembled: AssembledContext) -> dict[str, Any]:
    """將編排結果轉為可 merge 進 EvoLoop state 的欄位。"""
    injection = assembled.render_injection()
    return {
        "recall_context": {
            "injection": injection,
            "fragments": assembled.fragments,
            "reason_codes": assembled.reason_codes,
            "degraded_sources": assembled.degraded_sources,
            "token_report": assembled.token_report,
        },
        "history": list(assembled.history),
    }


def enhance_with_recall_context(state: StateInput) -> dict[str, Any]:
    """LangGraph／task_manager 節點：整合召回 fail-open 注入。"""
    query = str(state.get("query") or "")
    if not query.strip():
        return {}
    try:
        params = resolve_recall_params(state)
        assembled = assemble_recall_context(
            query,
            list(state.get("history") or []),
            user_id=params["user_id"],
            cube_ids=params["cube_ids"],
            knowledge_base_id=params["knowledge_base_id"],
        )
        update = assembled_to_state_update(assembled)
        if update["recall_context"]["injection"]:
            logger.info(
                "整合召回已注入（sources=%s, reason_codes=%s）",
                [f.get("source") for f in assembled.fragments],
                assembled.reason_codes,
            )
        return update
    except Exception as exc:
        logger.warning("整合召回 fail-open 略過：%s", exc)
        return {}


def prefix_query_with_recall(query: str, state: StateInput) -> str:
    """公司路徑：將召回片段前綴到任務 query（practical 注入）。"""
    recall = state.get("recall_context") or {}
    if not isinstance(recall, dict):
        return query
    injection = str(recall.get("injection") or "").strip()
    if not injection:
        return query
    return f"【整合召回上下文】\n{injection}\n\n【任務】\n{query}"
