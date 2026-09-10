"""EvoLoop 統一模式圖定義（單一管線：反思閉環 + 公司運行時 + OPC 整合）。

統一模式下不再區分「標準/公司/OPC」三種模式，所有任務
進入同一條 EvoLoop 管線，由系統自動判斷執行策略：

流程：
  START → retrieve_memories → enhance_with_opc_context → enhance_with_linkin_context → route_by_complexity
    → 複雜任務：run_company → should_evaluate_company
        → 成功：enforce_output_length → evaluate_answer → should_improve
            → (score < 門檻 且 未達最大迭代) → reflect → improve_answer → enforce_output_length（迴圈）
            → 否則 → decide_final_answer → enforce_final_length → save_memory → archive_state → END
        → 失敗：archive_state → END
    → 簡單任務：generate_initial_answer → enforce_output_length → evaluate_answer → should_improve
        → (score < 門檻 且 未達最大迭代) → reflect → improve_answer → enforce_output_length（迴圈）
        → 否則 → decide_final_answer → enforce_final_length → save_memory → archive_state → END

長度守門（enforce_output_length / enforce_final_length，同一實作的兩個地點）：
  超過依任務複雜度解析出的輸出上限時寫入 length_directive，
  由 should_rewrite_length 路由回 reflect，讓閉環把「精簡」當成一項改進目標；
  重寫預算（EVOL_MAX_LENGTH_REWRITES，預設 2 次）用盡後改交付歷次最短的一版並記警告。

執行策略（execution_strategy）：
  - "auto"（預設）: 依規則自動判斷複雜度
  - "simple": 強制單次 LLM 生成
  - "company": 強制多代理人公司運行時
"""

import logging
import os

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

from backend.core import nodes
from backend.core.company_nodes import (
    enhance_with_opc_context,
    route_by_complexity,
    run_company,
    should_evaluate_company,
)
from backend.core.state import EvoLoopState, StateInput
from backend.linkin.pipeline import enhance_with_linkin_context

# 可透過環境變數調整；測試中也可 monkeypatch 此模組常數
PASS_THRESHOLD = float(os.getenv("EVOL_PASS_THRESHOLD", "8"))
MAX_ITERATIONS = int(os.getenv("EVOL_MAX_ITERATIONS", "3"))
# 動態迭代：分數變化低於此值時提前終止（優化 #4）
MIN_SCORE_IMPROVEMENT = float(os.getenv("EVOL_MIN_SCORE_IMPROVEMENT", "0.5"))


def should_improve(state: StateInput) -> str:
    """條件路由（優化 #4：動態迭代策略）。

    終止條件（任一滿足即 finalize）：
    1. 分數已達門檻（依任務複雜度動態調整）
    2. 達到最大迭代次數
    3. 分數變化率過低（最近兩輪提升 < MIN_SCORE_IMPROVEMENT）
    """
    from backend.core.dynamic_threshold import resolve_pass_threshold

    score = state.get("score", 0.0)
    iteration = state.get("iteration", 0)
    pass_threshold = resolve_pass_threshold(state.get("query", ""))

    # 條件 1：已達門檻
    if score >= pass_threshold:
        return "finalize"

    # 條件 2：達最大迭代
    if iteration >= MAX_ITERATIONS:
        return "finalize"

    # 條件 3：分數變化率過低（提前終止）
    reflections = state.get("reflections", [])
    if len(reflections) >= 1:
        prev_score = reflections[-1].get("score", 0.0)
        improvement = score - prev_score
        if improvement < MIN_SCORE_IMPROVEMENT and iteration >= 1:
            logger.info(
                "動態迭代終止：分數提升 %.2f < 閾值 %.2f（第 %d 輪）",
                improvement, MIN_SCORE_IMPROVEMENT, iteration,
            )
            return "finalize"

    return "reflect"


def should_rewrite_length(state: StateInput) -> str:
    """條件路由：長度守門節點仍留有未消化的指令 → 丢回 reflect 重寫。"""
    return "rewrite" if state.get("length_directive") else "ok"


def build_graph():
    """組裝並編譯 EvoLoop 統一模式圖。"""
    graph = StateGraph(EvoLoopState)

    # ── 共用節點 ──
    graph.add_node("retrieve_memories", nodes.retrieve_memories)
    graph.add_node("enhance_with_opc_context", enhance_with_opc_context)
    graph.add_node("enhance_with_linkin_context", enhance_with_linkin_context)

    # ── 公司運行時節點 ──
    graph.add_node("run_company", run_company)

    # ── 生成/評估/反思節點 ──
    graph.add_node("generate_initial_answer", nodes.generate_initial_answer)
    graph.add_node("evaluate_answer", nodes.evaluate_answer)
    graph.add_node("reflect", nodes.reflect)
    graph.add_node("improve_answer", nodes.improve_answer)
    graph.add_node("enforce_output_length", nodes.enforce_output_length)
    graph.add_node("decide_final_answer", nodes.decide_final_answer)
    graph.add_node("enforce_final_length", nodes.enforce_final_length)
    graph.add_node("save_memory", nodes.save_memory)
    graph.add_node("archive_state", nodes.archive_state)

    # ── 統一管線入口 ──
    # START → 記憶檢索 → OPC 上下文增強 → 靈境 RAG 增強 → 複雜度路由
    graph.add_edge(START, "retrieve_memories")
    graph.add_edge("retrieve_memories", "enhance_with_opc_context")
    graph.add_edge("enhance_with_opc_context", "enhance_with_linkin_context")
    graph.add_conditional_edges(
        "enhance_with_linkin_context",
        route_by_complexity,
        {
            "run_company": "run_company",
            "generate_initial_answer": "generate_initial_answer",
        },
    )

    # ── 公司運行時路徑 ──
    # run_company → should_evaluate_company
    #   成功 → enforce_output_length（長度合規後進入評估/反思/改進迭代迴圈）
    #   失敗 → archive_state → END（跳過迭代）
    graph.add_conditional_edges(
        "run_company",
        should_evaluate_company,
        {"evaluate_answer": "enforce_output_length", "archive_state": "archive_state"},
    )

    # ── 簡單任務路徑 ──
    graph.add_edge("generate_initial_answer", "enforce_output_length")

    # ── 輸出長度守門（所有生成出口共用地點） ──
    # 超標 → 回到 reflect，由閉環把精簡當成一項改進目標；合規 → 進入評估
    graph.add_conditional_edges(
        "enforce_output_length",
        should_rewrite_length,
        {"rewrite": "reflect", "ok": "evaluate_answer"},
    )

    # ── 反思迭代迴圈（兩條路徑共用） ──
    graph.add_conditional_edges(
        "evaluate_answer",
        should_improve,
        {"reflect": "reflect", "finalize": "decide_final_answer"},
    )
    graph.add_edge("reflect", "improve_answer")
    graph.add_edge("improve_answer", "enforce_output_length")
    graph.add_edge("decide_final_answer", "enforce_final_length")
    graph.add_conditional_edges(
        "enforce_final_length",
        should_rewrite_length,
        {"rewrite": "reflect", "ok": "save_memory"},
    )
    graph.add_edge("save_memory", "archive_state")
    graph.add_edge("archive_state", END)

    return graph.compile()


# 供 API 層直接使用的編譯圖實例
evoloop_graph = build_graph()