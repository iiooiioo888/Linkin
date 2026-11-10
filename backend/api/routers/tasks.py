"""任務介面 API：後台任務建立、進度輪詢、取消／續跑、軌跡、Context 洞察與 WebSocket。

自 backend.main 抽出；函式體、回應結構與狀態碼不變，只把 `@app.*` 裝飾器改掛本模組
的 `router`，並把原本散落在端點內的延遲 import 集中到模組頂部。
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.auth.gate import ws_authorized
from backend.billing.context import billing_enabled, billing_task_id, current_billing_user
from backend.billing.errors import InsufficientCreditsError
from backend.billing.task_lifecycle import begin_billed_task, precheck_billed_task
from backend.core.execution_path import resolve_execution_path
from backend.services.cancelled_task_cleanup import cleanup_enabled, run_cleanup
from backend.services.context_insight import build_context_insight, resolve_default_task_id
from backend.services.monitor_hub import collect_monitor_hub
from backend.services.task_broadcaster import task_broadcaster
from backend.services.task_manager import task_manager
from backend.services.trace_logger import (
    list_checkpoints,
    list_traces,
    load_checkpoint,
    read_trace,
    trace_event_counts,
)
from backend.tenant.http import require_tenant_http, task_record_or_404
from backend.tenant.tasks import task_id_visible_for_tenant
from backend.tenant.ws import websocket_tenant_scope

router = APIRouter(tags=["tasks"])


class TaskRequest(BaseModel):
    query: str
    # 統一模式：執行策略（auto / simple / company），預設 auto 自動判斷
    execution_strategy: str = "auto"
    company_template: str = "quick_task"
    # 控制細項（進階參數）
    options: dict[str, Any] = {}


# 開工預算確認（上游 execution gate）請求模型
class BudgetDecisionRequest(BaseModel):
    action: str
    note: str = ""


class BudgetLinesRequest(BaseModel):
    lines: list[dict[str, Any]] = []


class ConfirmationDraftRequest(BaseModel):
    new_seats: list[dict[str, Any]] | None = None
    field_writes: list[dict[str, Any]] | None = None


class SeatOverrideRequest(BaseModel):
    role_id: str
    system_prompt: str | None = None
    tools_allowed: list[str] | None = None


class FieldWriteRetryRequest(BaseModel):
    field_writes: list[dict[str, Any]] | None = None


class NarrativeCommitRequest(BaseModel):
    kind: str
    entity: dict[str, Any] = {}


# ==================== 任務介面 API（後台執行 + 進度輪詢） ====================

@router.post("/tasks")
async def create_task(req: TaskRequest):
    """建立後台任務（統一模式），回傳 task_id 供輪詢。

    統一模式下不再區分模式，execution_strategy 僅為可選的強制指定：
    - "auto"（預設）: 系統自動判斷執行路徑
    - "simple": 強制單次 LLM 生成
    - "company": 強制公司運行時
    """
    require_tenant_http()
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="query 不可為空")

    record = task_manager.create_task(
        req.query, req.execution_strategy, req.company_template, options=req.options
    )
    path = resolve_execution_path(record.query, req.execution_strategy)
    record.resolved_path = "company" if path == "opc" else path
    billing_meta: dict = {}
    uid = current_billing_user()
    company_gate = record.resolved_path == "company"
    if billing_enabled() and uid:
        try:
            baseline = max(500, len(req.query) // 2)
            model = str((req.options or {}).get("model") or "default")
            if company_gate:
                # 公司路徑先「預檢」額度：確認開工後才真正扣款／保留。
                billing_meta = await asyncio.to_thread(
                    precheck_billed_task,
                    uid,
                    baseline_tokens=baseline,
                    model=model,
                )
            else:
                billing_meta = await asyncio.to_thread(
                    begin_billed_task,
                    uid,
                    task_id=record.task_id,
                    baseline_tokens=baseline,
                    model=model,
                )
                token = billing_task_id.set(record.task_id)
                record.options = {**(record.options or {}), "billing": billing_meta}
                task_manager._persist(record)
                billing_task_id.reset(token)
        except Exception as exc:
            if isinstance(exc, InsufficientCreditsError):
                raise HTTPException(status_code=402, detail=exc.message) from exc
            exc_cls = getattr(exc, "__class__", None)
            if exc_cls is not None and exc_cls.__name__ == "InsufficientCreditsError":
                raise HTTPException(status_code=402, detail=str(exc)) from exc
    if company_gate:
        # 公司任務先停在預算確認，使用者點頭才進席位執行。
        task_manager.start_budget_draft(record)
    else:
        task_manager.start_task(record)
    return {
        "task_id": record.task_id,
        "strategy": req.execution_strategy,
        "status": record.status,
        "awaiting_confirmation": company_gate,
        "pricing_version": billing_meta.get("pricing_config_version"),
        "reserved_credits": billing_meta.get("reserved_credits", 0),
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, events_limit: int = 50):
    """查詢任務進度：狀態、階段、事件流、看板、預算與結果。

    events_limit：回傳最近 N 條事件（0 或負值＝全部）。
    回應另帶 events_total 與 events_truncated 供前端提示截斷。
    """
    record = task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return record.to_dict(events_limit=events_limit)


@router.post("/tasks/{task_id}/budget/decision")
async def budget_decision(task_id: str, body: BudgetDecisionRequest):
    """批准或拒絕開工預算。拒絕與逾時都不進入席位執行。"""
    ok, message = task_manager.decide_budget(task_id, body.action, body.note)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record = task_manager.get_task(task_id)
    return {"success": True, "message": message, "task": record.to_dict() if record else None}


@router.post("/tasks/{task_id}/budget/lines")
async def budget_lines(task_id: str, body: BudgetLinesRequest):
    """能力負責人回填分項。確認前可改，確認後鎖定。"""
    ok, message = task_manager.update_budget_lines(task_id, body.lines)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record = task_manager.get_task(task_id)
    return {"success": True, "message": message, "budget_plan": record.budget_plan if record else None}


@router.post("/tasks/{task_id}/confirmation-draft")
async def confirmation_draft(task_id: str, body: ConfirmationDraftRequest):
    """點頭前改新席位草稿與現場寫入。不寫席位目錄，不改世界觀。"""
    ok, message = task_manager.update_confirmation_draft(
        task_id,
        new_seats=body.new_seats,
        field_writes=body.field_writes,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record = task_manager.get_task(task_id)
    return {"success": True, "message": message, "budget_plan": record.budget_plan if record else None}


@router.post("/tasks/{task_id}/seat-overrides")
async def seat_overrides(task_id: str, body: SeatOverrideRequest):
    """已存在席位的提示詞與工具權限立刻寫進目錄。"""
    ok, message = task_manager.apply_seat_override(
        task_id,
        body.role_id,
        system_prompt=body.system_prompt,
        tools_allowed=body.tools_allowed,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/tasks/{task_id}/field-writes")
async def field_writes(task_id: str, body: FieldWriteRetryRequest):
    """開工後重試現場寫入。整批通過檢查才寫。"""
    ok, message = task_manager.retry_field_writes(task_id, body.field_writes)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    record = task_manager.get_task(task_id)
    return {"success": True, "message": message, "budget_plan": record.budget_plan if record else None}


@router.post("/tasks/{task_id}/narrative/commit")
async def narrative_commit(task_id: str, body: NarrativeCommitRequest):
    """敘事顯式寫入實體。世界觀維持只讀。"""
    ok, message, stored = task_manager.commit_narrative(task_id, body.kind, body.entity)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message, "stored": stored}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """請求取消執行中的任務。

    設置取消標誌，任務會在下一個檢查點中止。
    已完成/已失敗的任務無法取消。
    """
    ok, message = task_manager.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """斷點續跑：從檢查點恢復任務執行。

    僅支援公司模式任務（有 orchestrator checkpoint）。
    """
    ok, message = task_manager.resume_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/admin/tasks/purge-cancelled")
async def admin_purge_cancelled_tasks():
    """手動觸發已取消任務過期清理（磁碟產物 + Redis 記錄）。"""
    if not cleanup_enabled():
        raise HTTPException(
            status_code=503,
            detail="清理已停用（LINKIN_CANCELLED_TASK_CLEANUP_ENABLED=false）",
        )
    try:
        summary = await asyncio.to_thread(run_cleanup, task_manager)
        return summary.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清理失敗：{exc}") from exc


# ==================== 思考過程軌跡 API ====================

@router.get("/tasks/{task_id}/trace")
async def get_task_trace(
    task_id: str,
    limit: int = 100,
    offset: int = 0,
    event: str | None = None,
    role: str | None = None,
    item_id: str | None = None,
    with_counts: bool = False,
):
    """獲取任務的思考過程記錄（分頁 + 可篩選）。

    記錄內容：LLM 調用、上下文注入、評估、反思、改進、階段切換，
    以及公司模式鏡像的全部角色事件（work_item_*/tool_*/review_*/grill_* 等）。
    event/role 支援逗號分隔多值；with_counts=true 附帶各事件型條數統計。
    """
    task_record_or_404(task_id)
    events = await asyncio.to_thread(
        read_trace, task_id, limit, offset,
        event=event, role=role, item_id=item_id,
    )
    result: dict = {"task_id": task_id, "offset": offset, "limit": limit, "events": events}
    if with_counts:
        result["event_counts"] = await asyncio.to_thread(trace_event_counts, task_id)
    return result


@router.get("/tasks/{task_id}/context")
async def get_task_context_insight(task_id: str, step: int | None = None):
    """Context 洞察（對齊 dsh-context：組成／趨勢／事件／瀏覽器）。

    從軌跡聚合，不觸發 LLM、不自動審計；``step`` 為 0-based llm_call 序號。
    """
    task_record_or_404(task_id)
    return await asyncio.to_thread(build_context_insight, task_id, step=step)


@router.get("/context")
async def get_context_insight(task_id: str | None = None, step: int | None = None):
    """Context 洞察快捷入口：可省略 task_id（取最新軌跡）。"""
    resolved = await asyncio.to_thread(resolve_default_task_id, task_id)
    if resolved and not task_id_visible_for_tenant(resolved):
        raise HTTPException(status_code=404, detail="任務不存在")
    if not resolved:
        return {
            "task_id": None,
            "stats": {},
            "composition": {},
            "trend": [],
            "events": [],
            "steps": [],
            "selected_step": None,
            "browser": {"step": None, "categories": {}, "vs_previous": None},
            "empty": True,
            "message": "尚無軌跡；先執行任務後再開啟 Context 面板。",
        }
    insight = await asyncio.to_thread(build_context_insight, resolved, step=step)
    insight["empty"] = False
    return insight


@router.get("/tasks/{task_id}/checkpoint")
async def get_task_checkpoint(task_id: str):
    """獲取任務的檢查點信息。"""
    task_record_or_404(task_id)
    checkpoint = await asyncio.to_thread(load_checkpoint, task_id)
    if checkpoint is None:
        return {"task_id": task_id, "exists": False}
    return {"task_id": task_id, "exists": True, "checkpoint": checkpoint}


@router.get("/traces")
async def get_traces(limit: int = 80):
    """列出所有思考過程軌跡檔案摘要。"""
    traces = await asyncio.to_thread(list_traces, limit)
    visible = [t for t in traces if task_id_visible_for_tenant(str(t.get("task_id") or ""))]
    return {"traces": visible}


@router.get("/checkpoints")
async def get_checkpoints():
    """列出所有可恢復的檢查點。"""
    checkpoints = await asyncio.to_thread(list_checkpoints)
    visible = [c for c in checkpoints if task_id_visible_for_tenant(str(c.get("task_id") or ""))]
    return {"checkpoints": visible}


@router.websocket("/tasks/{task_id}/ws")
async def task_websocket(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送任务进度。

    客户端连接后自动订阅任务事件，收到消息格式：
    {"task_id": "...", "event": "phase_change|evaluation|task_finished|...", "data": {...}}

    任务完成/失败后发送 task_finished 事件，客户端可主动关闭连接。
    """
    if not ws_authorized(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return

    async with websocket_tenant_scope(websocket):
        record = task_manager.get_task(task_id)
        if record is None:
            await websocket.close(code=4004, reason="任务不存在")
            return

        await websocket.accept()
        await task_broadcaster.subscribe(task_id, websocket)

        try:
            await websocket.send_json({
                "task_id": task_id,
                "event": "snapshot",
                "data": record.to_dict(),
            })

            while True:
                try:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_json({"task_id": task_id, "event": "pong", "data": {}})
                    elif data == "close":
                        break
                except WebSocketDisconnect:
                    break
        finally:
            await task_broadcaster.unsubscribe(task_id, websocket)


@router.websocket("/monitor/ws")
async def monitor_hub_websocket(websocket: WebSocket):
    """監控中心彙總推送：每 3 秒推送一次 hub-snapshot。

    訊息格式：{"event": "snapshot"|"pong", "data": {...}}
    """
    if not ws_authorized(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return

    async with websocket_tenant_scope(websocket):
        await websocket.accept()
        try:
            while True:
                snap = await asyncio.to_thread(collect_monitor_hub)
                await websocket.send_json({"event": "snapshot", "data": snap})

                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=3.0)
                    if data == "close":
                        break
                    if data == "ping":
                        await websocket.send_json({"event": "pong", "data": {}})
                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break
        except WebSocketDisconnect:
            pass
