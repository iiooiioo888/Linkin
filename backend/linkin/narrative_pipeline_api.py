"""Phase 5：敘事 RPG 一鍵管線 REST。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.linkin.narrative_pipeline import PIPELINE_STEP_ORDER, STEP_LABELS, run_narrative_pipeline

pipeline_router = APIRouter(prefix="/linkin/narrative/pipelines", tags=["linkin-narrative-pipeline"])


@pipeline_router.post("/run")
def pipeline_run(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """一鍵執行敘事 RPG 管線。

    - ``confirm_world=false``（預設）：begin → generate → commit → map_generate → previews
    - ``confirm_world=true``：在上述基礎上執行 build／world／map apply
    """
    payload = body or {}
    brief = str(payload.get("brief") or payload.get("seed") or "").strip()
    workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "").strip()
    if not brief and not workspace_id and not payload.get("use_starter_pack"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "message": "需要 brief、workspace_id 或 use_starter_pack=true",
                "code": "missing_input",
            },
        )
    result = run_narrative_pipeline(payload)
    if result.get("error_code") == "ERR_SNAPSHOT_UNRESOLVED":
        raise HTTPException(status_code=409, detail=result)
    return {"ok": result.get("ok", False), **result}


@pipeline_router.get("/steps")
def pipeline_steps() -> dict[str, Any]:
    """列出管線步驟定義（供前端 stepper 使用）。"""
    return {
        "steps": [
            {"id": step_id, "label": STEP_LABELS.get(step_id, step_id)}
            for step_id in PIPELINE_STEP_ORDER
        ]
    }


def register_narrative_pipeline_routes(app) -> None:
    app.include_router(pipeline_router)


__all__ = ["pipeline_router", "register_narrative_pipeline_routes"]
