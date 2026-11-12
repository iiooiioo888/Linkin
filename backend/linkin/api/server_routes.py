"""靈境 REST：服務器運維智能體端點。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from backend.tools.server_admin import ServerAdminError

from .router import linkin_router

# ── 服務器運維智能體（本地定制，恢復自 server_admin 模組）──
_SERVER_ERROR_STATUS = {
    "unknown_tool": 400,
    "invalid": 400,
    "invalid_service": 400,
    "path_denied": 403,
    "service_denied": 403,
    "dangerous_input": 403,
    "expired": 409,
    "invalid_state": 409,
    "needs_confirmation": 409,
}


def _server_http(exc: ServerAdminError) -> HTTPException:
    status = _SERVER_ERROR_STATUS.get(str(exc.code), 500)
    return HTTPException(
        status_code=status,
        detail={"message": str(exc), "code": exc.code, **exc.extra},
    )


@linkin_router.get("/server/health")
def server_health() -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    return server_ops.health_snapshot()


@linkin_router.post("/server/ask")
def server_ask(body: dict[str, Any]) -> dict[str, Any]:
    """自然語言運維問答：讀操作即執行；寫操作轉 pending_approval。"""
    from backend.linkin import server_admin as server_ops

    question = str(body.get("question") or body.get("command") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="需要 question")
    auto_approve = bool(body.get("auto_approve"))
    role = str(body.get("role") or "").strip()
    try:
        return server_ops.ask_agent(question, auto_approve=auto_approve, role=role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ServerAdminError as exc:
        raise _server_http(exc) from exc


@linkin_router.get("/server/approvals")
def server_approvals(include_done: bool = Query(False)) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    items = server_ops.list_approvals(include_done=include_done)
    return {"approvals": items, "count": len(items)}


@linkin_router.post("/server/approvals/{approval_id}/confirm")
def server_approval_confirm(approval_id: str) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    try:
        return server_ops.confirm_approval(approval_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServerAdminError as exc:
        raise _server_http(exc) from exc


@linkin_router.post("/server/approvals/{approval_id}/cancel")
def server_approval_cancel(approval_id: str) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    try:
        return server_ops.cancel_approval(approval_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServerAdminError as exc:
        raise _server_http(exc) from exc


@linkin_router.post("/server/patrol")
def server_patrol(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """主動巡檢：健康快照 + 規則提案（預設轉人工批准；不自動執行破壞性操作）。"""
    from backend.linkin import server_admin as server_ops

    auto_approve = bool((body or {}).get("auto_approve"))
    return server_ops.patrol(auto_approve=auto_approve)


@linkin_router.get("/server/report")
def server_report() -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    return {"report": server_ops.daily_report()}


@linkin_router.get("/server/audit")
def server_audit(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    rows = server_ops.audit_tail(limit)
    return {"entries": rows, "count": len(rows)}
