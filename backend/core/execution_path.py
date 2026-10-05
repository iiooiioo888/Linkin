"""統一執行路徑解析（Task API、SSE、LangGraph route_by_complexity 共用）。

優先序（auto）：
  1. 強制策略 simple / company
  2. OPC 工業關鍵詞 → opc（僅 Task API 分派；圖與 SSE 不進 OPC 六級）
  3. 靈境複雜任務 → company
  4. Minecraft 控制查詢 → company
  5. cost_speed 分類與 path 配置 → company | simple
  6. 關鍵詞／長度規則 → company | simple
"""

from __future__ import annotations

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

_COMPANY_KEYWORDS = re.compile(
    r"(开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|"
    r"多步|架構|架构|重构|遷移|迁移|deploy|develop|build|implement|design|"
    r"create|refactor|migrate|project|system|application|"
    r"故事|小說|小说|撰寫|撰写|長文|长文|\d+\s*字)",
    re.IGNORECASE,
)

_OPC_KEYWORDS = re.compile(
    r"(感測|传感|溫度|温度|壓力|压力|流量|閥門|阀门|閥|阀|馬達|马达|電機|电机|"
    r"設備|设备|製程|制程|工業|工业|產線|产线|opc|sensor|temperature|pressure|"
    r"flow|valve|motor|equipment|industrial|plc)",
    re.IGNORECASE,
)

_COMPLEX_QUERY_LENGTH = 200


def _complex_query_length() -> int:
    try:
        from backend.core.routing_feedback import adaptive_length_threshold

        return adaptive_length_threshold(_COMPLEX_QUERY_LENGTH)
    except Exception:
        return _COMPLEX_QUERY_LENGTH


def is_complex_task(query: str) -> bool:
    """規則判斷任務是否複雜（需要公司運行時）。"""
    threshold = _complex_query_length()
    if len(query) >= threshold:
        return True
    return bool(_COMPANY_KEYWORDS.search(query))


def needs_opc_context(query: str) -> bool:
    """判斷任務是否需要 OPC 工業上下文。"""
    return bool(_OPC_KEYWORDS.search(query))

ExecutionPath = Literal["simple", "company", "opc"]


def resolve_execution_path(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
) -> ExecutionPath:
    """解析查詢應走的執行路徑。"""
    strat = (strategy or "auto").strip().lower()
    text = query or ""

    if strat == "simple":
        return "simple"
    if strat == "company":
        return "company"

    if needs_opc_context(text):
        return "opc"

    try:
        from backend.linkin.pipeline import is_linkin_complex_task
        from backend.tools.minecraft_mcp import is_minecraft_control_query

        if is_linkin_complex_task(text):
            logger.debug("execution_path: linkin complex → company")
            return "company"
        if is_minecraft_control_query(text):
            logger.debug("execution_path: minecraft control → company")
            return "company"
    except Exception as exc:
        logger.debug("execution_path: linkin/minecraft 判斷略過：%s", exc)

    try:
        from backend.core.cost_speed_router import (
            classify_task_complexity,
            cost_speed_enabled,
            resolve_path_for_complexity,
        )

        if cost_speed_enabled():
            level = task_complexity or classify_task_complexity(text)
            path = resolve_path_for_complexity(level)  # type: ignore[arg-type]
            if path == "company":
                logger.debug("execution_path: cost_speed %s → company", level)
                return "company"
            return "simple"
    except Exception as exc:
        logger.warning("execution_path: cost_speed 失敗，回退規則：%s", exc)

    if is_complex_task(text):
        return "company"
    return "simple"


def route_by_complexity_target(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
) -> Literal["run_company", "generate_initial_answer"]:
    """LangGraph 條件邊名稱。"""
    path = resolve_execution_path(query, strategy, task_complexity=task_complexity)
    if path == "company":
        return "run_company"
    return "generate_initial_answer"


def chat_stream_uses_company_sse(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
) -> bool:
    """SSE /chat/stream 是否走公司運行時串流（不含 OPC 六級）。"""
    return resolve_execution_path(query, strategy, task_complexity=task_complexity) == "company"
