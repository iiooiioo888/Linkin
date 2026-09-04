"""EvoLoop 統一模式節點（單一管線：反思閉環 + 公司運行時 + OPC 整合）。

統一模式下不再區分「標準/公司/OPC」三種模式，而是單一 EvoLoop 管線：

    記憶檢索 → OPC 上下文增強（自動） → 靈境 RAG 增強（自動） → 複雜度路由
      ├─ 簡單任務 → 單次 LLM 生成
      └─ 複雜任務 → 公司運行時（分解→執行→審查→整合）
    → 評估 → 反思 → 改進（迭代迴圈） → 存檔

本模組提供以下節點：
- enhance_with_opc_context: OPC 服務可用時自動注入工業數據上下文
- route_by_complexity: 依執行策略與任務複雜度決定生成路徑
- run_company: 執行完整公司運行流程，將產出設為 current_answer
- should_evaluate_company: 公司執行後路由（成功→評估迭代，失敗→直接存檔）
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from backend.company.orchestrator import CompanyOrchestrator
from backend.company.roles import BUILTIN_TEMPLATES
from backend.core.state import EvoLoopState

logger = logging.getLogger(__name__)

# ─── 複雜度判斷規則 ───────────────────────────────────────────

# 觸發公司運行時的關鍵詞（複雜任務特徵）
_COMPANY_KEYWORDS = re.compile(
    r"(开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|"
    r"多步|架構|架构|重构|遷移|迁移|deploy|develop|build|implement|design|"
    r"create|refactor|migrate|project|system|application)",
    re.IGNORECASE,
)

# 觸發 OPC 上下文注入的工業關鍵詞
_OPC_KEYWORDS = re.compile(
    r"(感測|传感|溫度|温度|壓力|压力|流量|閥門|阀门|閥|阀|馬達|马达|電機|电机|"
    r"設備|设备|製程|制程|工業|工业|產線|产线|opc|sensor|temperature|pressure|"
    r"flow|valve|motor|equipment|industrial|plc)",
    re.IGNORECASE,
)

# 複雜任務的 query 長度門檻（字符數，P2 自適應反饋可動態調整）
_COMPLEX_QUERY_LENGTH = 200


def _complex_query_length() -> int:
    try:
        from backend.core.routing_feedback import adaptive_length_threshold
        return adaptive_length_threshold(_COMPLEX_QUERY_LENGTH)
    except Exception:
        return _COMPLEX_QUERY_LENGTH


def _is_complex_task(query: str) -> bool:
    """規則判斷任務是否複雜（需要公司運行時）。"""
    threshold = _complex_query_length()
    if len(query) >= threshold:
        return True
    return bool(_COMPANY_KEYWORDS.search(query))


def _needs_opc_context(query: str) -> bool:
    """判斷任務是否需要 OPC 工業上下文。"""
    return bool(_OPC_KEYWORDS.search(query))


# ─── OPC 上下文增強節點 ──────────────────────────────────────


def enhance_with_opc_context(state: EvoLoopState) -> dict[str, Any]:
    """OPC 上下文增強：query 涉及工業關鍵詞時自動注入感測數據。

    統一模式下 OPC 整合不再是獨立模式，而是管線中的
    上下文增強步驟。OPC 服務不可用時靜默降級（不中斷主流程）。
    """
    query = state.get("query", "")
    if not _needs_opc_context(query):
        return {"opc_context": {}}

    try:
        from opc_service.sense import sense_opc

        try:
            result = asyncio.run(sense_opc(dict(state)))
        except RuntimeError:
            # 已有事件迴圈（LangGraph ainvoke 場景）→ 同步降級
            logger.debug("事件迴圈存在，跳過 OPC 非同步感知")
            return {"opc_context": {}}

        readings = result.get("opc_readings", {})
        if not readings:
            return {"opc_context": {}}

        # 將讀數摘要注入上下文
        summary_lines = ["【工業數據上下文（OPC 即時讀數）】"]
        for tag, info in readings.items():
            summary_lines.append(f"- {tag}: {info.get('value')} (品質: {info.get('quality', 'Good')})")

        return {
            "opc_context": {
                "readings": readings,
                "summary": "\n".join(summary_lines),
            }
        }
    except Exception as exc:  # noqa: BLE001 - OPC 不可用時靜默降級
        logger.warning("OPC 上下文增強失敗（降級跳過）：%s", exc)
        return {"opc_context": {}}


# ─── 複雜度路由節點 ──────────────────────────────────────────


def route_by_complexity(state: EvoLoopState) -> str:
    """條件路由：依執行策略與任務複雜度決定生成路徑。

    執行策略（execution_strategy）：
    - "simple": 強制單次 LLM 生成
    - "company": 強制公司運行時
    - "auto"（預設）: 依 cost_speed 配置或規則自動判斷複雜度

    回傳值：
    - "run_company": 走公司運行時
    - "generate_initial_answer": 走單次生成
    """
    strategy = state.get("execution_strategy", "auto")

    if strategy == "simple":
        return "generate_initial_answer"
    if strategy == "company":
        return "run_company"

    query = state.get("query", "")
    complexity = state.get("task_complexity")

    try:
        from backend.linkin.pipeline import is_linkin_complex_task
        from backend.tools.minecraft_mcp import is_minecraft_control_query

        if is_linkin_complex_task(query):
            logger.info("靈境世界觀任務判定為複雜，啟用公司運行時")
            return "run_company"
        if is_minecraft_control_query(query):
            logger.info("Minecraft MCP 控制任務判定為複雜，啟用公司運行時")
            return "run_company"
    except Exception as exc:  # noqa: BLE001
        logger.debug("靈境／Minecraft 複雜度判斷略過：%s", exc)

    try:
        from backend.core.cost_speed_router import (
            classify_task_complexity,
            cost_speed_enabled,
            resolve_path_for_complexity,
        )

        if cost_speed_enabled():
            level = complexity or classify_task_complexity(query)
            path = resolve_path_for_complexity(level)  # type: ignore[arg-type]
            if path == "company":
                logger.info("cost_speed 判定為 %s，啟用公司運行時", level)
                return "run_company"
            return "generate_initial_answer"
    except Exception as exc:  # noqa: BLE001
        logger.warning("cost_speed 路徑路由失敗，回退規則判斷：%s", exc)

    # auto：規則判斷（向後相容）
    if _is_complex_task(query):
        logger.info("任務判定為複雜，啟用公司運行時")
        return "run_company"
    return "generate_initial_answer"


# ─── 公司運行時節點 ──────────────────────────────────────────


def run_company(state: EvoLoopState) -> dict[str, Any]:
    """執行公司運行時：多角色分工完成目標。

    成功時將公司產出設為 current_answer，交由 evaluate_answer
    進入反思迭代迴圈（與簡單任務共用同一評估/反思/改進管線）；
    失敗時直接設定 final_answer 並跳過迭代。

    這是同步包裝器，內部使用 asyncio.run 呼叫非同步協調器。
    """
    query = state.get("query", "")
    template_name = state.get("company_template", "quick_task")

    try:
        from backend.linkin.pipeline import prefix_query_with_linkin, resolve_linkin_company_template

        linkin_template = resolve_linkin_company_template(state)
        if linkin_template:
            template_name = linkin_template
        query = prefix_query_with_linkin(query, state)
    except Exception as exc:  # noqa: BLE001
        logger.debug("靈境公司前綴略過：%s", exc)

    # 選擇組織架構模板
    config = BUILTIN_TEMPLATES.get(template_name)
    if config is None:
        logger.warning("未知模板 %s，使用 quick_task", template_name)
        config = BUILTIN_TEMPLATES["quick_task"]

    orchestrator = CompanyOrchestrator(config)

    try:
        # 在同步節點中執行非同步協調器
        try:
            loop = asyncio.get_running_loop()
            # 已有事件迴圈，建立新任務
            result = asyncio.run_coroutine_threadsafe(
                orchestrator.execute(query), loop
            ).result(timeout=300)
        except RuntimeError:
            # 無事件迴圈，使用 asyncio.run
            result = asyncio.run(orchestrator.execute(query))

        final_output = result.get("final_output", "")

        # 成功：將產出設為 current_answer，交由 evaluate_answer 評估迭代
        return {
            "current_answer": final_output,
            "company_result": result,
            "company_kanban": result.get("kanban", {}),
            "company_budget": result.get("budget", {}),
            "iteration": 0,
        }

    except Exception as exc:  # noqa: BLE001 - 降級兜底：公司運行時失敗不中斷主流程
        logger.error("公司運行時執行失敗：%s", exc)
        # 失敗：直接設定 final_answer，跳過評估迭代
        return {
            "final_answer": f"公司運行時執行失敗：{exc}",
            "company_result": {"success": False, "error": str(exc)},
            "company_kanban": {},
            "company_budget": {},
            "iteration": 0,
            "score": 0.0,
            "evaluation": {"score": 0, "strengths": "", "weaknesses": str(exc)},
        }


def should_evaluate_company(state: EvoLoopState) -> str:
    """公司運行時執行後路由（優化 #2：錯誤回退策略）。

    路由邏輯：
    - 成功 → evaluate_answer（進入評估迭代迴圈）
    - 失敗但有部分產出 → evaluate_answer（嘗試用反思閉環修復）
    - 失敗且無產出 → archive_state → END

    與 should_improve 配合，構成公司運行時的完整迭代路徑。
    """
    company_result = state.get("company_result", {})
    if company_result.get("success", False):
        return "evaluate_answer"

    # 優化 #2：失敗時嘗試回退到簡單模式
    # 如果公司運行時產出了部分結果（final_output 非空），
    # 將其交給反思閉環繼續優化，而非直接丟棄
    final_output = state.get("final_answer", "") or state.get("current_answer", "")
    if final_output and len(final_output.strip()) > 50:
        logger.info(
            "公司運行時失敗但有部分產出（%d 字），回退到反思閉環優化",
            len(final_output),
        )
        # 將部分產出設為 current_answer，進入評估迭代
        return "evaluate_answer"

    return "archive_state"