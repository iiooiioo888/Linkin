# patch_runtime_followup.py — one-shot helper (safe to delete)
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ADDON = '''

def button_enabled(state: TaskRuntimeState | str, action: TaskAction | str) -> bool:
    """C-UI-002：前端按鈕可用性以後端矩陣為準。

    DENY → 禁用；ALLOW／SEQUENCE／QUEUE → 可點（QUEUE 由後端佇列，UI 可提交）。
    """
    return evaluate(state, action).verdict is not Verdict.DENY


def export_matrix() -> dict:
    """匯出可序列化矩陣供 GUI／契約測試對照（C-UI-002）。"""
    cells: list[dict] = []
    for (state, action), decision in _MATRIX.items():
        cells.append(
            {
                "state": state.value,
                "action": action.value,
                "verdict": decision.verdict.value,
                "next_state": decision.next_state.value if decision.next_state else None,
                "error_code": decision.error_code,
                "note": decision.note,
                "button_enabled": decision.verdict is not Verdict.DENY,
            }
        )
    return {
        "states": [s.value for s in TaskRuntimeState],
        "actions": [a.value for a in TaskAction],
        "cells": cells,
        "schema": "todo-§9-v1",
    }
'''

RUNTIME_API = r'''"""運行時契約 HTTP 面：狀態矩陣／效能預算（C-UI-002／C-PERF-001）。

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
'''


def patch_task_state_machine() -> None:
    path = ROOT / "backend" / "company" / "task_state_machine.py"
    text = path.read_text(encoding="utf-8")
    if "def button_enabled" in text:
        print("task_state_machine: already patched")
        return
    if "def queued_pairs()" not in text:
        raise SystemExit("queued_pairs missing")
    # append after last function
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + ADDON, encoding="utf-8")
    print("task_state_machine: patched")


def write_runtime_api() -> None:
    path = ROOT / "backend" / "company" / "runtime_api.py"
    path.write_text(RUNTIME_API, encoding="utf-8")
    print("runtime_api: written")


def patch_main() -> None:
    path = ROOT / "backend" / "main.py"
    text = path.read_text(encoding="utf-8")
    if "register_runtime_api" in text:
        print("main: already wired")
        return
    needle = "register_integrations(app)\n"
    insert = (
        "register_integrations(app)\n"
        "from backend.company.runtime_api import register_runtime_api  # noqa: E402\n"
        "\n"
        "register_runtime_api(app)\n"
    )
    if needle not in text:
        raise SystemExit("register_integrations needle missing")
    path.write_text(text.replace(needle, insert, 1), encoding="utf-8")
    print("main: wired")


if __name__ == "__main__":
    patch_task_state_machine()
    write_runtime_api()
    patch_main()
    print("done")
