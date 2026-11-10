"""RAHO 質詢／裁決與需求審計官 API（自 backend.main 抽出）。

/raho/* 與 /auditor/* 端點；SSE 端點沿用原 main.py 的串流格式。
"""

import json as json_mod
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["raho"])


class RahoGrillStartBody(BaseModel):
    query: str
    execution_strategy: str = "auto"


class RahoGrillTurnBody(BaseModel):
    session_id: str
    answer: str = ""
    force_lock: bool = False


class RahoDecideBody(BaseModel):
    decision_id: str
    choice: str
    note: str = ""


class RahoCommanderPlanBody(BaseModel):
    ticket: dict[str, Any] | None = None
    locked_brief: str = ""
    use_llm: bool | None = None


class RahoCommanderGrillBody(BaseModel):
    message: str
    allowed_tools: list[str] = []
    alternative_fields: list[str] = []
    priority_ruling: str = ""
    rounds_used: int = 0
    item_id: str = ""


@router.post("/raho/grill/start")
def raho_grill_start(body: RahoGrillStartBody) -> dict[str, Any]:
    """L5→L4 用戶需求審計官：五維鎖定第一問。"""
    from backend.company.raho.grill_user import grill_user_start, should_grill_user

    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query 不可為空")
    if not should_grill_user(query, body.execution_strategy):
        return {
            "should_grill": False,
            "locked": True,
            "confidence": 1.0,
            "locked_brief": query,
            "session_id": "",
            "question": None,
        }
    try:
        return grill_user_start(query)
    except Exception as exc:
        logger.warning("RAHO grill_start 失敗，降級直通：%s", exc)
        return {
            "should_grill": False,
            "locked": True,
            "confidence": 0.5,
            "locked_brief": query,
            "session_id": "",
            "question": None,
            "degraded": True,
        }


@router.post("/raho/grill/turn")
def raho_grill_turn(body: RahoGrillTurnBody) -> dict[str, Any]:
    """繼續需求審計，或將『直接執行』視為過度授權。"""
    from backend.company.raho.grill_user import grill_user_lock, grill_user_turn

    try:
        if body.force_lock:
            return grill_user_lock(body.session_id, body.answer)
        return grill_user_turn(body.session_id, body.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/raho/grill/status")
def raho_grill_status() -> dict[str, Any]:
    from backend.company.raho.grill_user import grill_user_status

    return grill_user_status()


class AuditorStreamBody(BaseModel):
    query: str = ""
    session_id: str = ""
    answer: str = ""
    force_lock: bool = False


@router.post("/auditor/start")
def auditor_gateway_start(body: RahoGrillStartBody) -> dict[str, Any]:
    """強制前置閘門：直接開審，不因寒暄跳過。"""
    from backend.services.auditor import auditor_start

    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query 不可為空")
    try:
        return auditor_start(query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/auditor/turn")
def auditor_gateway_turn(body: RahoGrillTurnBody) -> dict[str, Any]:
    """繼續需求審計。force_lock 視同過度授權，觸發終止協議。"""
    from backend.services.auditor import auditor_lock, auditor_turn

    try:
        if body.force_lock:
            return auditor_lock(body.session_id, body.answer)
        return auditor_turn(body.session_id, body.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/auditor/status")
def auditor_gateway_status() -> dict[str, Any]:
    from backend.services.auditor import auditor_status

    return auditor_status()


@router.post("/auditor/stream")
def auditor_gateway_stream(body: AuditorStreamBody) -> StreamingResponse:
    """SSE：把審計官本輪拷問與五維評分推給前端。"""
    from backend.services.auditor import auditor_lock, auditor_start, auditor_turn

    def _events():
        try:
            if (body.session_id or "").strip():
                if body.force_lock:
                    result = auditor_lock(body.session_id, body.answer)
                else:
                    result = auditor_turn(body.session_id, body.answer)
            else:
                query = (body.query or "").strip()
                if not query:
                    raise ValueError("query 不可為空")
                result = auditor_start(query)
        except (KeyError, ValueError) as exc:
            yield f"event: error\ndata: {json_mod.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            return
        question = ((result.get("question") or {}) or {}).get("question") or ""
        if question:
            yield f"event: question\ndata: {json_mod.dumps({'text': question}, ensure_ascii=False)}\n\n"
        if result.get("scores"):
            yield f"event: scores\ndata: {json_mod.dumps(result['scores'], ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json_mod.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/raho/tree")
def raho_tree(run_id: str | None = None) -> dict[str, Any]:
    """遞歸質詢樹與決策阻塞點。"""
    from backend.company.raho.store import STORE

    if run_id:
        tree = STORE.get_tree(run_id)
        from backend.company.raho.l0 import kernel_snapshot

        return {
            "tree": tree.to_dict() if tree else None,
            "pending_decisions": [
                p.to_dict() for p in STORE.list_pending(run_id) if p.resolution is None
            ],
            "l0": kernel_snapshot(query=str(getattr(tree, "goal", "") or "")),
        }
    return STORE.snapshot()


@router.get("/raho/l0")
def raho_l0(query: str = "", node_id: str = "") -> dict[str, Any]:
    """L0 環境與記憶核心：記憶軌跡、知識實體、態勢雷達。"""
    from backend.company.raho.l0 import kernel_snapshot

    return kernel_snapshot(query=query, node_id=node_id)


@router.post("/raho/decide")
def raho_decide(body: RahoDecideBody) -> dict[str, Any]:
    """L5 用戶介入熱馬桶圈裁決。"""
    from backend.company.raho.escalation import decide as decide_escalation

    try:
        return decide_escalation(body.decision_id, body.choice, body.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/raho/commander/plan")
def raho_commander_plan(body: RahoCommanderPlanBody) -> dict[str, Any]:
    """L3 戰術指揮官：把 L4 門票拆成原子作戰地圖。"""
    from backend.company.raho.commander import command_from_ticket

    source = body.ticket or body.locked_brief
    if not source:
        raise HTTPException(status_code=422, detail="需要 ticket 或 locked_brief")
    kwargs: dict[str, Any] = {}
    if body.use_llm is not None:
        kwargs["use_llm"] = body.use_llm
    return command_from_ticket(source, **kwargs)


@router.post("/raho/commander/grill")
def raho_commander_grill(body: RahoCommanderGrillBody) -> dict[str, Any]:
    """L3 回應 L2 [GRILL] 質詢（SOP 決策樹）。"""
    from backend.company.raho.commander import command_grill
    from backend.services.commander import increment_grill_round

    rounds = body.rounds_used
    if body.item_id:
        rounds = increment_grill_round(body.item_id) - 1
    return command_grill(
        body.message,
        allowed_tools=body.allowed_tools,
        alternative_fields=body.alternative_fields,
        priority_ruling=body.priority_ruling,
        rounds_used=max(0, rounds),
    )


@router.post("/raho/commander/grill/stream")
def raho_commander_grill_stream(body: RahoCommanderGrillBody) -> StreamingResponse:
    """L3 對 L2 [GRILL] 的即時裁決（SSE）。"""
    from backend.company.raho.commander import command_grill
    from backend.services.commander import increment_grill_round

    def _events():
        rounds = body.rounds_used
        if body.item_id:
            rounds = increment_grill_round(body.item_id) - 1
        result = command_grill(
            body.message,
            allowed_tools=body.allowed_tools,
            alternative_fields=body.alternative_fields,
            priority_ruling=body.priority_ruling,
            rounds_used=max(0, rounds),
        )
        yield f"event: sop\ndata: {json_mod.dumps({'kind': result.get('kind'), 'escalate': result.get('escalate')}, ensure_ascii=False)}\n\n"
        if result.get("reply"):
            yield f"event: reply\ndata: {json_mod.dumps({'text': result['reply']}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json_mod.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/raho/scorecard")
def raho_scorecard() -> dict[str, Any]:
    from backend.company.raho.scorecard import all_metrics

    return {"roles": all_metrics()}
