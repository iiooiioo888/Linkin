"""指揮鏈的工業執行。

公司指揮鏈與 OPC 是同一條：感知、預處理、分析、診斷、決策、執行
就是 L0 到 L2 的工業步驟。寫入仍經 opc_service 護欄。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from backend.core.opc_degrade import note_opc_from_sense_result
from opc_service.act import act_opc
from opc_service.analyze import analyze_opc
from opc_service.decide import decide_opc
from opc_service.diagnose import diagnose_opc
from opc_service.preprocess import preprocess_opc
from opc_service.sense import sense_opc

PhaseHook = Callable[[str, dict[str, Any]], Awaitable[bool | None] | bool | None]

def _stages() -> tuple[tuple[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]], ...]:
    return (
        ("sense_opc", sense_opc),
        ("preprocess_opc", preprocess_opc),
        ("analyze_opc", analyze_opc),
        ("diagnose_opc", diagnose_opc),
        ("decide_opc", decide_opc),
        ("act_opc", act_opc),
    )


def assemble_industrial_answer(state: dict[str, Any]) -> str:
    """把六級結果收成指揮鏈的交付。"""
    diagnosis = state.get("opc_diagnosis", {}) or {}
    analysis = state.get("opc_analysis", {}) or {}
    quality = state.get("opc_quality_report", {}) or {}
    decisions = state.get("opc_decisions", []) or []
    actions = state.get("opc_actions", []) or []

    answer_parts = ["## 指揮鏈 · 工業執行\n"]
    answer_parts.append(
        f"**數據品質**：總標籤 {quality.get('total', 0)}，"
        f"良好 {quality.get('good', 0)}，不良 {quality.get('bad', 0)}"
    )
    answer_parts.append(f"**統計分析**：{analysis.get('summary', '無')}")
    answer_parts.append(
        f"**診斷結果**：{'⚠️ 檢測到異常' if diagnosis.get('anomaly_detected') else '✅ 無異常'}\n"
        f"- 嚴重程度：{diagnosis.get('severity', 'normal')}\n"
        f"- 根因分析：{diagnosis.get('root_cause', '無')}\n"
        f"- 詳細分析：{diagnosis.get('analysis', '無')}"
    )
    if decisions:
        answer_parts.append(f"**控制決策**：{state.get('opc_decision_summary', '')}")
        for i, decision in enumerate(decisions):
            answer_parts.append(
                f"{i + 1}. {decision.get('tag_name', '?')} → "
                f"{decision.get('value', '?')} "
                f"（優先級：{decision.get('priority', '?')}，"
                f"風險：{decision.get('risk', '?')}）"
            )
    else:
        answer_parts.append("**控制決策**：無需執行控制動作")
    if actions:
        success = sum(1 for action in actions if action.get("success"))
        answer_parts.append(f"**執行結果**：{success}/{len(actions)} 成功")
    return "\n\n".join(answer_parts)


async def _hook(on_phase: PhaseHook | None, phase: str, state: dict[str, Any]) -> bool:
    if on_phase is None:
        return True
    result = on_phase(phase, state)
    if hasattr(result, "__await__"):
        result = await result  # type: ignore[misc]
    return result is not False


async def run_industrial_chain(
    state: dict[str, Any],
    on_phase: PhaseHook | None = None,
) -> dict[str, Any]:
    """跑完指揮鏈的工業步驟。on_phase 回傳 False 時停下並標 cancelled。"""
    for phase, step in _stages():
        update = await step(state)
        if isinstance(update, dict):
            state.update(update)
        if phase == "sense_opc":
            note_opc_from_sense_result(state)
        if not await _hook(on_phase, phase, state):
            state["cancelled"] = True
            return state
    state["current_answer"] = assemble_industrial_answer(state)
    return state
