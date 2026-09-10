"""運行時契約 HTTP 面：狀態矩陣／效能預算（C-UI-002／C-PERF-001）。

端點：
- ``GET  /runtime/state-matrix``：§9 矩陣完整匯出（GUI 按鈕可用性來源）
- ``POST /runtime/state-matrix/evaluate``：查詢 (state, action) 決策
- ``GET  /runtime/perf-budgets``：P95 預設上限
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.company.task_state_machine import (
    TaskAction,
    TaskRuntimeState,
    button_enabled,
    evaluate,
    export_matrix,
)
from backend.core.perf_budget import DEFAULT_P95_SECONDS, check_elapsed

router = APIRouter(prefix="/runtime", tags=["runtime"])


class EvaluateRequest(BaseModel):
    state: str = Field(..., description="TaskRuntimeState 值")
    action: str = Field(..., description="TaskAction 值")


class PerfCheckRequest(BaseModel):
    action: str
    elapsed_seconds: float
    overrides: dict[str, float] | None = None


@router.get("/state-matrix")
def get_state_matrix() -> dict[str, Any]:
    """C-UI-002：前端禁止自行發明矩陣；以此端點為準。"""
    return export_matrix()


@router.post("/state-matrix/evaluate")
def evaluate_state_action(req: EvaluateRequest) -> dict[str, Any]:
    try:
        state = TaskRuntimeState(req.state)
        action = TaskAction(req.action)
    except ValueError as exc:
        return {
            "ok": False,
            "error_code": "ERR_INVALID_STATE_OR_ACTION",
            "detail": str(exc),
        }
    decision = evaluate(state, action)
    return {
        "ok": True,
        "state": state.value,
        "action": action.value,
        "verdict": decision.verdict.value,
        "next_state": decision.next_state.value if decision.next_state else None,
        "error_code": decision.error_code,
        "note": decision.note,
        "button_enabled": button_enabled(state, action),
    }


@router.get("/perf-budgets")
def get_perf_budgets() -> dict[str, Any]:
    """C-PERF-001：P95 預設上限（秒）。"""
    return {"p95_seconds": dict(DEFAULT_P95_SECONDS), "unit": "seconds"}


@router.post("/perf-budgets/check")
def post_perf_check(req: PerfCheckRequest) -> dict[str, Any]:
    """以 stub 耗時驗證預算邏輯（測試／監控用）。"""
    result = check_elapsed(req.action, req.elapsed_seconds, overrides=req.overrides)
    return result.to_dict()


def register_runtime_api(app: Any) -> None:
    app.include_router(router)
