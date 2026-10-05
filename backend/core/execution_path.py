"""統一執行路徑解析（Task API、SSE、LangGraph route_by_complexity 共用）。

優先序（auto）：
  1. 強制策略 simple / company
  2. OPC 工業關鍵詞 → opc（僅 Task API 分派；圖與 SSE 不進 OPC 六級）
  3. 靈境複雜任務 → company
  4. Minecraft 重型任務（建造／敘事／多步） → company
  5. Minecraft 單步控制查詢 → minecraft_ops（輕量 ReAct + MCP）
  6. cost_speed 分類與 path 配置 → company | simple
  7. 關鍵詞／長度規則 → company | simple
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

_MC_HEAVY_RE = re.compile(
    r"(建造|建筑|建築|扩建|擴建|改建|主城|聚落|城堡|宫殿|宮殿|"
    r"NPC|角色卡|任务|任務|主线|主線|支线|支線|道具|附魔|"
    r"世界观|世界觀|宪法|憲法|"
    r"narrative|敘事|story_studio|map\s*plan|地圖計畫|build\s*brief|建築落地|"
    r"待落地|世界意圖|schematic|結構|结构|藍圖|蓝图|"
    r"多步|多個地標|沿途|批量建造|完整.*城)",
    re.IGNORECASE,
)

_NARRATIVE_PIPELINE_RE = re.compile(
    r"(narrative|敘事|管線|pipeline|phase\s*[0-5]|"
    r"map\s*plan|地圖計畫|build\s*brief|建築落地|"
    r"世界意圖|待落地|story_studio)",
    re.IGNORECASE,
)

_MC_LINKIN_SCOPE_RE = re.compile(
    r"(minecraft|minemcp|mine\s*mcp|灵境|靈境|linkin|story_studio)",
    re.IGNORECASE,
)


def _is_mc_or_linkin_scoped(query: str) -> bool:
    """敘事／管線關鍵詞僅在 MC 或靈境語境下才視為重型。"""
    text = query or ""
    if _MC_LINKIN_SCOPE_RE.search(text):
        return True
    try:
        from backend.linkin.pipeline import needs_linkin_context
        from backend.tools.minecraft_mcp import is_minecraft_control_query

        return needs_linkin_context(text) or is_minecraft_control_query(text)
    except Exception:
        return False


def _complex_query_length() -> int:
    try:
        from backend.core.routing_feedback import adaptive_length_threshold

        return adaptive_length_threshold(_COMPLEX_QUERY_LENGTH)
    except Exception:
        return _COMPLEX_QUERY_LENGTH


def is_complex_task(query: str, *, use_routing_feedback: bool = True) -> bool:
    """規則判斷任務是否複雜（需要公司運行時）。"""
    threshold = (
        _complex_query_length()
        if use_routing_feedback
        else _COMPLEX_QUERY_LENGTH
    )
    if len(query) >= threshold:
        return True
    return bool(_COMPANY_KEYWORDS.search(query))


def needs_opc_context(query: str) -> bool:
    """判斷任務是否需要 OPC 工業上下文。"""
    return bool(_OPC_KEYWORDS.search(query))


def is_minecraft_heavy_task(query: str) -> bool:
    """Minecraft 相關且需多席位／敘事／設計，不走輕量 ops。"""
    text = query or ""
    try:
        from backend.linkin.pipeline import is_linkin_complex_task

        if is_linkin_complex_task(text):
            return True
    except Exception:
        pass
    if _is_mc_or_linkin_scoped(text) and _NARRATIVE_PIPELINE_RE.search(text):
        return True
    try:
        from backend.tools.minecraft_mcp import is_minecraft_control_query

        if not is_minecraft_control_query(text):
            return False
    except Exception:
        return False
    if _MC_HEAVY_RE.search(text):
        return True
    # 輕量 ops 分類不受 routing_feedback 字數門檻上調影響
    return is_complex_task(text, use_routing_feedback=False)


def is_minecraft_ops_query(query: str) -> bool:
    """單步／少步 Minecraft MCP 操作（輕量路徑）。"""
    text = query or ""
    try:
        from backend.tools.minecraft_mcp import is_minecraft_control_query

        return bool(is_minecraft_control_query(text)) and not is_minecraft_heavy_task(text)
    except Exception:
        return False


ExecutionPath = Literal["simple", "company", "opc", "minecraft_ops"]


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
        if is_linkin_complex_task(text):
            logger.debug("execution_path: linkin complex → company")
            return "company"
        if is_minecraft_heavy_task(text):
            logger.debug("execution_path: minecraft heavy → company")
            return "company"
        if is_minecraft_ops_query(text):
            logger.debug("execution_path: minecraft ops → minecraft_ops")
            return "minecraft_ops"
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
) -> Literal["run_company", "run_minecraft_ops", "generate_initial_answer"]:
    """LangGraph 條件邊名稱。"""
    path = resolve_execution_path(query, strategy, task_complexity=task_complexity)
    if path == "company":
        return "run_company"
    if path == "minecraft_ops":
        return "run_minecraft_ops"
    return "generate_initial_answer"


def chat_stream_uses_company_sse(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
) -> bool:
    """SSE /chat/stream 是否走公司運行時串流（不含 OPC 六級）。"""
    return resolve_execution_path(query, strategy, task_complexity=task_complexity) == "company"
