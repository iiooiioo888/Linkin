"""Phase 4 區域地圖 REST：generate / preview / apply。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.linkin.knowledge import COL_EVENTS, upsert_entity
from backend.linkin.map_plan import (
    MapPlanError,
    apply_map_plan,
    gather_narrative_context,
    generate_map_plan,
    preview_map_plan,
    validate_map_plan,
)
from backend.linkin.narrative_registry import get_narrative_registry
from backend.linkin.tools import ToolValidationError

map_router = APIRouter(prefix="/linkin/map", tags=["linkin-map"])


def _tool_http(exc: ToolValidationError) -> HTTPException:
    status = 409 if exc.code == "needs_confirmation" else 400
    return HTTPException(
        status_code=status,
        detail={"message": str(exc), "code": exc.code, **exc.extra},
    )


def _parse_origin(body: dict[str, Any]) -> dict[str, int] | None:
    origin = body.get("origin")
    if not origin:
        return None
    from backend.tools import minecraft_mcp as mcp

    xyz = mcp.parse_xyz(origin)
    if xyz is None and isinstance(origin, dict):
        return {"x": int(origin["x"]), "y": int(origin["y"]), "z": int(origin["z"])}
    if xyz:
        return {"x": xyz[0], "y": xyz[1], "z": xyz[2]}
    raise HTTPException(status_code=400, detail={"message": "origin 無法解析"})


def _plan_http(exc: MapPlanError) -> HTTPException:
    status = 400
    if exc.code in {"plot_limit", "block_limit", "axis_limit"}:
        status = 413
    return HTTPException(status_code=status, detail={"message": str(exc), "code": exc.code})


def _load_workspace_drafts(workspace_id: str) -> dict[str, Any]:
    ws = get_narrative_registry().get(workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error_code": "ERR_WORKSPACE_UNKNOWN", "workspace_id": workspace_id},
        )
    return dict(ws.drafts)


@map_router.post("/generate")
def map_generate(body: dict[str, Any]) -> dict[str, Any]:
    """從工作區草稿或已提交實體生成 map_plan；可選 LLM，失敗 fallback。"""
    workspace_id = str(body.get("workspace_id") or body.get("workspaceId") or "").strip()
    region = str(body.get("region") or "").strip() or None
    seed = str(body.get("seed") or body.get("region_seed") or "").strip() or None
    origin = _parse_origin(body) if body.get("origin") else None

    drafts: dict[str, Any] = {}
    if workspace_id:
        drafts = _load_workspace_drafts(workspace_id)

    context = gather_narrative_context(workspace_drafts=drafts, region=region)
    seed_value = seed or context.get("region") or "map-seed"
    generated = generate_map_plan(context=context, seed=seed_value, origin=origin)
    plan = generated["plan"]
    preview = preview_map_plan(plan)
    saved = upsert_entity("map_plans", {**plan, "status": "planned"})
    return {
        "ok": True,
        "source": generated.get("source") or "fallback",
        "plan": saved,
        "preview": preview,
    }


@map_router.post("/preview")
def map_preview(body: dict[str, Any]) -> dict[str, Any]:
    """預覽 map_plan：邊界、plot 數、預估方塊、POI 列表；不寫世界。"""
    plan = body.get("plan")
    plan_id = str(body.get("plan_id") or body.get("planId") or "").strip()
    if plan is None and plan_id:
        from backend.linkin.knowledge import list_entities

        matches = [p for p in list_entities("map_plans") if str(p.get("id")) == plan_id]
        if not matches:
            raise HTTPException(status_code=404, detail={"message": f"map_plan 不存在：{plan_id}"})
        plan = matches[0]
    if not isinstance(plan, dict):
        raise HTTPException(status_code=400, detail={"message": "需要 plan 或 plan_id"})
    try:
        preview = preview_map_plan(plan)
    except MapPlanError as exc:
        raise _plan_http(exc) from exc
    return {"ok": True, "preview": preview}


@map_router.post("/apply")
def map_apply(body: dict[str, Any]) -> dict[str, Any]:
    """落地 map_plan；需 confirm=true。bridge 關閉時 dry-run。部分失敗回傳 partial。"""
    confirmed = bool(body.get("confirm") or body.get("confirmed"))
    plan = body.get("plan")
    plan_id = str(body.get("plan_id") or body.get("planId") or "").strip()
    if plan is None and plan_id:
        from backend.linkin.knowledge import list_entities

        matches = [p for p in list_entities("map_plans") if str(p.get("id")) == plan_id]
        if not matches:
            raise HTTPException(status_code=404, detail={"message": f"map_plan 不存在：{plan_id}"})
        plan = matches[0]
    if not isinstance(plan, dict):
        raise HTTPException(status_code=400, detail={"message": "需要 plan 或 plan_id"})

    if not confirmed:
        try:
            validated = validate_map_plan(plan)
        except MapPlanError as exc:
            raise _plan_http(exc) from exc
        raise HTTPException(
            status_code=409,
            detail={
                "message": "地圖落地需 confirm=true",
                "code": "needs_confirmation",
                "needs_confirmation": True,
                "plan_id": validated["id"],
                "preview": preview_map_plan(validated),
            },
        )

    try:
        result = apply_map_plan(plan, confirmed=True)
    except MapPlanError as exc:
        raise _plan_http(exc) from exc
    except ToolValidationError as exc:
        raise _tool_http(exc) from exc

    validated = validate_map_plan(plan)
    status = str(result.get("status") or "complete")
    updated = upsert_entity(
        "map_plans",
        {
            **validated,
            "status": "applied" if status == "complete" else ("partial" if status == "partial" else "failed"),
            "mcp": {
                "ok": result.get("ok"),
                "dry_run": result.get("dry_run"),
                "blocks_placed": result.get("blocks_placed"),
                "applied_count": len(result.get("applied") or []),
                "error_count": len(result.get("errors") or []),
            },
        },
    )
    from backend.linkin.knowledge import get_store

    get_store().upsert(
        COL_EVENTS,
        f"地圖落地 {validated['id']} → Minecraft MCP（status={status} dry_run={result.get('dry_run')}）",
        {"kind": "minecraft", "map_plan_id": validated["id"], "status": status},
        skip_quality=True,
    )
    return {"ok": result.get("ok"), "plan": updated, "minecraft": result, "status": status}


def register_map_routes(app) -> None:
    app.include_router(map_router)


__all__ = ["map_router", "register_map_routes"]
