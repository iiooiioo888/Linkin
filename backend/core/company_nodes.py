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
import json
import logging
from typing import Any

from backend.company.orchestrator import CompanyOrchestrator
from backend.company.roles import BUILTIN_TEMPLATES
from backend.core.state import StateInput

logger = logging.getLogger(__name__)

# ─── 複雜度判斷規則（實作於 execution_path，此處保留相容別名） ──

from backend.core.execution_path import (
    is_complex_task as _is_complex_task,
    needs_opc_context as _needs_opc_context,
)


# ─── OPC 上下文增強節點 ──────────────────────────────────────


def enhance_with_opc_context(state: StateInput) -> dict[str, Any]:
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
    except Exception as exc:
        logger.warning("OPC 上下文增強失敗（降級跳過）：%s", exc)
        return {"opc_context": {}}


# ─── 複雜度路由節點 ──────────────────────────────────────────


def route_by_complexity(state: StateInput) -> str:
    """條件路由：依執行策略與任務複雜度決定生成路徑。

    執行策略（execution_strategy）：
    - "simple": 強制單次 LLM 生成
    - "company": 強制公司運行時
    - "auto"（預設）: 依 cost_speed 配置或規則自動判斷複雜度

    回傳值：
    - "run_company": 走公司運行時
    - "generate_initial_answer": 走單次生成
    """
    from backend.core.execution_path import route_by_complexity_target

    query = state.get("query", "")
    target = route_by_complexity_target(
        query,
        str(state.get("execution_strategy", "auto")),
        task_complexity=state.get("task_complexity"),
    )
    if target == "run_company":
        logger.info("任務解析為公司運行時（query 前 80 字）：%s", query[:80])
    return target


# ─── 公司運行時節點 ──────────────────────────────────────────


def run_company(state: StateInput) -> dict[str, Any]:
    """執行公司運行時：多角色分工完成目標。

    成功時將公司產出設為 current_answer，交由 evaluate_answer
    進入反思迭代迴圈（與簡單任務共用同一評估/反思/改進管線）；
    失敗時直接設定 final_answer 並跳過迭代。

    這是同步包裝器，內部使用 asyncio.run 呼叫非同步協調器。
    """
    query = state.get("query", "")
    lock = state.get("semantic_lock") or {}
    if isinstance(lock, dict):
        if lock.get("locked_brief"):
            query = str(lock["locked_brief"])
        elif isinstance(lock.get("ticket"), dict):
            query = json.dumps(lock["ticket"], ensure_ascii=False)
    template_name = state.get("company_template", "quick_task")

    try:
        from backend.linkin.pipeline import (
            prefix_query_with_linkin,
            resolve_linkin_company_template,
        )

        linkin_template = resolve_linkin_company_template(state)
        if linkin_template:
            template_name = linkin_template
        query = prefix_query_with_linkin(query, state)
    except Exception as exc:
        logger.debug("靈境公司前綴略過：%s", exc)

    try:
        from backend.integrations.recall_bridge import prefix_query_with_recall

        query = prefix_query_with_recall(query, state)
    except Exception as exc:
        logger.debug("整合召回公司前綴略過：%s", exc)

    # 選擇組織架構模板
    config = BUILTIN_TEMPLATES.get(template_name)
    if config is None:
        logger.warning("未知模板 %s，使用 quick_task", template_name)
        config = BUILTIN_TEMPLATES["quick_task"]

    orchestrator = CompanyOrchestrator(config)
    ticket = lock.get("ticket") if isinstance(lock, dict) else None
    ticket = ticket if isinstance(ticket, dict) else None

    try:
        # 在同步節點中執行非同步協調器
        try:
            loop = asyncio.get_running_loop()
            # 已有事件迴圈，建立新任務
            result = asyncio.run_coroutine_threadsafe(
                orchestrator.execute(query, ticket=ticket), loop
            ).result(timeout=300)
        except RuntimeError:
            # 無事件迴圈，使用 asyncio.run
            result = asyncio.run(orchestrator.execute(query, ticket=ticket))

        final_output = result.get("final_output", "")

        # 成功：將產出設為 current_answer，交由 evaluate_answer 評估迭代
        from backend.core.post_company_reflect import post_company_reflect_mode

        return {
            "current_answer": final_output,
            "company_result": result,
            "company_kanban": result.get("kanban", {}),
            "company_budget": result.get("budget", {}),
            "iteration": 0,
            "post_company_reflect_mode": post_company_reflect_mode(),
        }

    except Exception as exc:
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


def should_evaluate_company(state: StateInput) -> str:
    """公司運行時執行後路由（優化 #2：錯誤回退策略）。

    路由邏輯：
    - 成功 + 預設 post reflect off → 直接定稿（與 Task/SSE 一致）
    - 成功 + evaluate/full → 進入評估／反思閉環
    - 失敗但有部分產出 → evaluate_answer（嘗試用反思閉環修復）
    - 失敗且無產出 → archive_state → END

    與 should_improve 配合，構成公司運行時的完整迭代路徑。
    """
    company_result = state.get("company_result", {})
    if company_result.get("success", False):
        mode = str(state.get("post_company_reflect_mode") or "").strip().lower()
        if not mode:
            from backend.core.post_company_reflect import post_company_reflect_mode

            mode = post_company_reflect_mode()
        if mode == "off":
            return "company_finalize"
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