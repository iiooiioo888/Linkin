"""節點 1-2（自 backend.core.nodes 抽出）。

節點 1-2：初始生成與多維度評估。
"""

from __future__ import annotations

from backend.core.evaluation import CrossModelEvaluator, get_evaluator
from backend.core.pipeline_trace import log_node
from backend.core.stage_router import resolve_stage_model
from backend.core.state import StateInput
from backend.prompts.templates import truncate

from ._compat import call_llm
from .prompt_build import build_generate_prompt


def generate_initial_answer(state: StateInput) -> dict:
    """節點 1：生成初始回答。"""
    prompt, system = build_generate_prompt(state)
    model = resolve_stage_model(
        "generate",
        query=state.get("query"),
        complexity=state.get("task_complexity"),
    )
    answer = call_llm(prompt, system=system, model=model)
    log_node(state, "generate_initial_answer", model=model)
    return {
        "initial_answer": answer,
        "current_answer": answer,
        "iteration": 0,
        # 軌跡回填用：實際使用的模型、系統提示詞與完整生成 prompt
        "generate_model": model,
        "generate_system": system,
        "generate_prompt": prompt,
    }


def evaluate_answer(state: StateInput) -> dict:
    """節點 2：多維度自動評估，產出 0-10 分與評語。

    評估流程（優化 #1）：
    1. LLM 多維度評估（4 維度獨立打分）
    2. 解析失敗 → 規則啟發式 fallback（不再一律 0 分）
    3. 可選：交叉評估（不同模型覆核，打破自評偏差）
    """
    query = state["query"]
    answer = state["current_answer"]

    # 截斷長回答以節省評估 token（優化 #14）
    truncated_answer = truncate(answer, 4000)

    # 多維度評估（內部已含規則 fallback）
    evaluator = get_evaluator()
    eval_result = evaluator.evaluate(query, truncated_answer)

    # 可選：交叉評估覆核
    cross_result = CrossModelEvaluator.cross_evaluate(
        query, answer, eval_result.to_dict()
    )
    if cross_result is not None:
        eval_result = cross_result

    score = eval_result.overall
    evaluation = eval_result.to_dict()
    log_node(state, "evaluate_answer", score=score, source=eval_result.source)

    # 向後相容：保留舊版 evaluation 格式
    legacy_evaluation = {
        "score": score,
        "strengths": f"準確性{eval_result.accuracy.score:.1f} 完整性{eval_result.completeness.score:.1f}",
        "weaknesses": f"清晰度{eval_result.clarity.score:.1f} 相關性{eval_result.relevance.score:.1f}",
    }

    return {
        "score": score,
        "evaluation": legacy_evaluation,
        "multi_dim_evaluation": evaluation,
    }
