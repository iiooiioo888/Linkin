"""生成階段 prompt 與 system 組裝。（自 backend.core.nodes 抽出）。

生成階段 prompt 與 system 組裝。
"""

from __future__ import annotations

from backend.core.state import StateInput
from backend.prompts import templates
from backend.prompts.templates import truncate

from .memory import _format_history, _format_memories


def _format_injected_context(state: StateInput) -> str:
    """OPC／靈境／整合召回上下文摘要，注入生成 prompt。"""
    parts: list[str] = []
    opc = state.get("opc_context") or {}
    if isinstance(opc, dict) and opc.get("summary"):
        parts.append(str(opc["summary"]))
    linkin = state.get("linkin_context") or {}
    if isinstance(linkin, dict) and linkin.get("summary"):
        parts.append(str(linkin["summary"]))
    recall = state.get("recall_context") or {}
    if isinstance(recall, dict):
        injection = str(recall.get("injection") or "").strip()
        if injection:
            parts.append(f"【整合召回】\n{injection}")
    if not parts:
        return ""
    return "\n".join(parts) + "\n"


def _generate_system_prompt(state: StateInput) -> str:
    from backend.core.locale_prompt import ui_language_system_overlay

    system = templates.GENERATE_INITIAL_ANSWER_SYSTEM
    raw_lang = state.get("ui_language")
    ui_lang = raw_lang if isinstance(raw_lang, str) else None
    locale_line = ui_language_system_overlay(ui_lang)
    if locale_line:
        system = f"{locale_line}\n\n{system}"
    linkin = state.get("linkin_context") or {}
    if isinstance(linkin, dict) and linkin.get("active") and linkin.get("system_overlay"):
        return f"{linkin['system_overlay']}\n{system}"
    return system


def build_generate_prompt(state: StateInput) -> tuple[str, str]:
    """組裝初始生成 prompt 與 system（graph／SSE 共用）。"""
    extra = _format_injected_context(state)
    memory = _format_memories(state.get("retrieved_memories", []))
    prompt = templates.GENERATE_INITIAL_ANSWER.format(
        query=truncate(state["query"], 2000),
        history_context=truncate(_format_history(state.get("history", [])), 2000),
        memory_context=truncate(extra + memory, 2000),
    )
    return prompt, _generate_system_prompt(state)
