"""OPC 6 级思考闭环图编排（優化 #10：超時降級 + 人工確認）。

组装 6 级工业闭环流程：
  sense → preprocess → analyze → diagnose → decide → act → END

每級帶超時降級：
  - 超時 → 使用上一級緩存結果繼續
  - 關鍵決策級（act）→ 可選人工確認
"""

import asyncio
import logging
import os
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from opc_service.act import act_opc
from opc_service.analyze import analyze_opc
from opc_service.decide import decide_opc
from opc_service.diagnose import diagnose_opc
from opc_service.preprocess import preprocess_opc
from opc_service.sense import sense_opc
from opc_service.state import OPCStateFields

logger = logging.getLogger(__name__)

# 每級超時（秒），可透過環境變數覆蓋
OPC_STAGE_TIMEOUT = int(os.getenv("OPC_STAGE_TIMEOUT", "30"))
OPC_ACT_HUMAN_CONFIRM = os.getenv("OPC_ACT_HUMAN_CONFIRM", "false").lower() == "true"


async def _with_timeout_and_fallback(
    stage_fn: Callable,
    stage_name: str,
    state: dict,
    timeout: int = OPC_STAGE_TIMEOUT,
    fallback_keys: list[str] | None = None,
) -> dict[str, Any]:
    """執行 OPC 階段，帶超時降級（優化 #10）。

    Args:
        stage_fn: 階段函數
        stage_name: 階段名稱（用於日誌）
        state: 當前狀態
        timeout: 超時秒數
        fallback_keys: 超時時從 state 中讀取的 fallback 鍵

    Returns:
        階段輸出（正常或降級）
    """
    try:
        if asyncio.iscoroutinefunction(stage_fn):
            result = await asyncio.wait_for(stage_fn(state), timeout=timeout)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(stage_fn, state), timeout=timeout
            )
        return result
    except asyncio.TimeoutError:
        logger.warning(
            "OPC 階段 %s 超時（%ds），使用降級結果",
            stage_name, timeout,
        )
        # 嘗試從 state 中讀取 fallback 數據
        fallback: dict[str, Any] = {}
        if fallback_keys:
            for key in fallback_keys:
                if key in state:
                    fallback[key] = state[key]
        fallback["_degraded"] = True
        fallback["_degraded_stage"] = stage_name
        fallback["_degraded_reason"] = f"{stage_name} 超時（{timeout}s）"
        return fallback
    except Exception as exc:
        logger.error("OPC 階段 %s 異常：%s", stage_name, exc)
        fallback = {"_degraded": True, "_degraded_stage": stage_name, "_degraded_reason": str(exc)}
        if fallback_keys:
            for key in fallback_keys:
                if key in state:
                    fallback[key] = state[key]
        return fallback


async def sense_opc_safe(state: dict) -> dict:
    """S1 感知（帶超時降級）。"""
    return await _with_timeout_and_fallback(
        sense_opc, "sense", state, fallback_keys=["opc_readings"]
    )


async def preprocess_opc_safe(state: dict) -> dict:
    """P1 預處理（帶超時降級）。"""
    return await _with_timeout_and_fallback(
        preprocess_opc, "preprocess", state, fallback_keys=["opc_readings_clean"]
    )


async def analyze_opc_safe(state: dict) -> dict:
    """A1 分析（帶超時降級）。"""
    return await _with_timeout_and_fallback(
        analyze_opc, "analyze", state, fallback_keys=["opc_analysis"]
    )


async def diagnose_opc_safe(state: dict) -> dict:
    """Dg1 診斷（帶超時降級）。"""
    return await _with_timeout_and_fallback(
        diagnose_opc, "diagnose", state, fallback_keys=["opc_diagnosis"]
    )


async def decide_opc_safe(state: dict) -> dict:
    """D1 決策（帶超時降級）。"""
    return await _with_timeout_and_fallback(
        decide_opc, "decide", state, fallback_keys=["opc_decision"]
    )


async def act_opc_safe(state: dict) -> dict:
    """A2 執行（帶超時降級 + 可選人工確認）。"""
    # 人工確認機制（優化 #10）
    if OPC_ACT_HUMAN_CONFIRM:
        decision = state.get("opc_decision", {})
        actions = decision.get("actions", [])
        if actions:
            logger.info(
                "OPC 執行級：需要人工確認 %d 個控制動作（OPC_ACT_HUMAN_CONFIRM=true）",
                len(actions),
            )
            # 在人工確認模式下，將動作標記為待確認，不自動執行
            return {
                "opc_act_result": {
                    "executed": [],
                    "pending_confirmation": actions,
                    "summary": f"{len(actions)} 個動作待人工確認",
                    "human_confirm_required": True,
                },
            }

    return await _with_timeout_and_fallback(
        act_opc, "act", state, fallback_keys=["opc_act_result"]
    )


def build_opc_graph():
    """組裝 OPC 6 級思考閉環圖（帶超時降級）。

    流程：sense_opc_safe → preprocess_opc_safe → analyze_opc_safe
           → diagnose_opc_safe → decide_opc_safe → act_opc_safe → END

    此圖可獨立使用，也可作為 EvoLoop 主圖的子圖。
    """
    graph = StateGraph(OPCStateFields)

    graph.add_node("sense_opc", sense_opc_safe)
    graph.add_node("preprocess_opc", preprocess_opc_safe)
    graph.add_node("analyze_opc", analyze_opc_safe)
    graph.add_node("diagnose_opc", diagnose_opc_safe)
    graph.add_node("decide_opc", decide_opc_safe)
    graph.add_node("act_opc", act_opc_safe)

    graph.add_edge("sense_opc", "preprocess_opc")
    graph.add_edge("preprocess_opc", "analyze_opc")
    graph.add_edge("analyze_opc", "diagnose_opc")
    graph.add_edge("diagnose_opc", "decide_opc")
    graph.add_edge("decide_opc", "act_opc")
    graph.add_edge("act_opc", END)

    graph.set_entry_point("sense_opc")

    return graph.compile()


# 供 API 层直接使用的编译图实例
opc_graph = build_opc_graph()