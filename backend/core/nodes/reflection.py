"""節點 3-4（自 backend.core.nodes 抽出）。

節點 3-4：反思與改進。
"""

from __future__ import annotations

import json

from backend.core.llm import parse_json_response
from backend.core.pipeline_trace import log_node
from backend.core.stage_router import resolve_stage_model
from backend.core.state import StateInput
from backend.prompts import templates

from ._compat import call_llm
from .memory import _search_reflection_hints


def _length_requirement(state: StateInput) -> str:
    """長度守門節點尚未消化的硬性要求，注入反思與改進 prompt。"""
    directive = state.get("length_directive", "")
    return f"{directive}\n" if directive else ""


def reflect(state: StateInput) -> dict:
    """節點 3：針對低分回答進行反思（優化 #4：分層反思）。

    分層策略：
    - 低分（< 5）：深度反思，傳入完整多維度評估 + 強調根因分析
    - 中分（5-8）：表面修正，傳入摘要評估 + 聚焦具體改進點
    - 相似問題的歷史反思可注入為參考（反思結果復用）
    """
    score = state.get("score", 0.0)
    multi_dim = state.get("multi_dim_evaluation", {})
    reflection_hints = _search_reflection_hints(state.get("query", ""))
    try:
        from backend.company.raho.scorecard import reflection_notes

        grill_notes = reflection_notes(state.get("company_result") or {})
        if grill_notes:
            reflection_hints = (reflection_hints or "") + grill_notes + "\n"
    except Exception:
        pass
    try:
        from backend.company.horizon import horizon_prompt_block

        horizon_notes = horizon_prompt_block()
        if horizon_notes:
            reflection_hints = (reflection_hints or "") + horizon_notes
    except Exception:
        pass

    # 分層反思：根據分數選擇反思深度
    if score < 5.0:
        # 深度反思：傳入完整多維度評估細節
        eval_detail = json.dumps(multi_dim, ensure_ascii=False) if multi_dim else json.dumps(state.get("evaluation", {}), ensure_ascii=False)
    else:
        # 表面修正：只傳入摘要，節省 token
        if multi_dim:
            eval_summary = {
                "overall": multi_dim.get("overall", 0),
                "weakest": min(
                    [
                        (d, float(entry.get("score", 10)))
                        for d in ("accuracy", "completeness", "clarity", "relevance")
                        for entry in [multi_dim.get(d)]
                        if isinstance(entry, dict)
                    ],
                    key=lambda x: x[1],
                )[0],
            }
            eval_detail = json.dumps(eval_summary, ensure_ascii=False)
        else:
            eval_detail = json.dumps(state.get("evaluation", {}), ensure_ascii=False)
    prompt = _length_requirement(state) + reflection_hints + templates.REFLECT.format(
        query=state["query"],
        answer=state["current_answer"],
        score=score,
        evaluation=eval_detail,
    )

    model = resolve_stage_model(
        "reflect",
        query=state.get("query"),
        complexity=state.get("task_complexity"),
    )
    raw = call_llm(prompt, model=model)
    try:
        result = parse_json_response(raw)
    except json.JSONDecodeError:
        # LLM 未遵守 JSON 格式時，將全文視為根因分析
        result = {"critique": raw, "suggestion": ""}
    log_node(state, "reflect", model=model, score=score)
    return {
        "critique": result.get("critique", ""),
        "suggestion": result.get("suggestion", ""),
    }


def improve_answer(state: StateInput) -> dict:
    """節點 4：根據反思結果優化回答，並累加迭代計數與反思紀錄。"""
    prompt = _length_requirement(state) + templates.IMPROVE_ANSWER.format(
        query=state["query"],
        answer=state["current_answer"],
        critique=state.get("critique", ""),
        suggestion=state.get("suggestion", ""),
    )
    model = resolve_stage_model(
        "improve",
        query=state.get("query"),
        complexity=state.get("task_complexity"),
    )
    improved = call_llm(prompt, model=model)
    iteration = state.get("iteration", 0) + 1
    try:
        from backend.billing.metering import meter_reflection_iteration

        meter_reflection_iteration(1, task_id=str(state.get("session_id") or ""), meta={"node": "improve_answer"})
    except Exception:
        pass
    log_node(state, "improve_answer", model=model, iteration=iteration)
    reflections = list(state.get("reflections", []))
    reflections.append(
        {
            "iteration": iteration,
            "score": state.get("score", 0.0),
            "critique": state.get("critique", ""),
            "suggestion": state.get("suggestion", ""),
        }
    )
    return {"current_answer": improved, "iteration": iteration, "reflections": reflections}
