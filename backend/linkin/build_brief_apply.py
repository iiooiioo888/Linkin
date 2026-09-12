"""Phase 2：建築意圖（build_brief）→ Schematic → MineMCP 落地。

消費 narrative commit 寫入的 ``build_briefs`` 實體，經既有 Builder／橋接護欄
生成 schematic 並以 ``place_block`` 分批落地。預覽（dry-run）不連線 MineMCP。
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.linkin.constitution import allowed_styles_for_region, max_blocks_per_call
from backend.linkin.design_llm import generate_llm_structure
from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_WORLDVIEW,
    get_store,
    list_entities,
    upsert_entity,
)
from backend.linkin.minecraft import execute_named_tool, monitor_status
from backend.linkin.schematic import (
    MAX_AXIS,
    Schematic,
    SchematicError,
    attach_model,
    attach_schematic,
    block_key,
    ensure_schematic,
    preview_payload,
)
from backend.linkin.tools import (
    TOOL_BUILDER_GENERATE,
    ToolValidationError,
    invoke_tool,
)
from backend.tools import minecraft_mcp as mcp

MAX_BLOCKS = 5000


class BuildBriefError(ValueError):
    """建築意圖校驗或落地失敗。"""

    def __init__(self, message: str, *, code: str = "invalid", extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


@dataclass
class BuildJob:
    job_id: str
    brief_id: str
    status: str = "pending"
    dry_run: bool = False
    blocks_total: int = 0
    blocks_placed: int = 0
    blocks_failed: int = 0
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


_jobs: dict[str, BuildJob] = {}
_jobs_lock = threading.Lock()


def _max_blocks() -> int:
    return min(MAX_BLOCKS, max_blocks_per_call() or MAX_BLOCKS)


def resolve_brief_style(brief: dict[str, Any]) -> str:
    """將陣營名或區域別名解析為 Builder 可接受的建築風格。"""
    region = str(brief.get("region") or "").strip()
    style = str(brief.get("style") or "").strip()
    allowed = allowed_styles_for_region(region)
    if allowed:
        if style in allowed:
            return style
        faction_allowed = allowed_styles_for_region(style)
        if faction_allowed:
            return faction_allowed[0]
        return allowed[0]
    if style:
        faction_allowed = allowed_styles_for_region(style)
        if faction_allowed:
            return faction_allowed[0]
        return style
    return "契约广场"


def validate_build_brief(brief: dict[str, Any]) -> dict[str, Any]:
    """校驗 build_brief 實體／payload，回傳標準化欄位。"""
    if not isinstance(brief, dict):
        raise BuildBriefError("build_brief 必須為 JSON 物件", code="invalid_schema")
    prompt = str(brief.get("prompt") or brief.get("description") or "").strip()
    if not prompt:
        raise BuildBriefError("build_brief 需要 prompt 或 description", code="missing_prompt")
    region = str(brief.get("region") or "织庭都").strip() or "织庭都"
    location = brief.get("location") or brief.get("coords") or "0,64,0"
    anchor = mcp.parse_xyz(location)
    if anchor is None:
        raise BuildBriefError("location 無法解析為 x,y,z", code="invalid_location")
    style = resolve_brief_style({**brief, "region": region})
    try:
        block_count = int(brief.get("block_count") or brief.get("blockCount") or 800)
    except (TypeError, ValueError) as exc:
        raise BuildBriefError("block_count 必須為整數", code="invalid_block_count") from exc
    limit = _max_blocks()
    if block_count <= 0:
        raise BuildBriefError("block_count 必須為正整數", code="block_limit")
    if block_count > limit:
        raise BuildBriefError(
            f"block_count 不得超過 {limit}（收到 {block_count}）",
            code="block_limit",
            extra={"block_count": block_count, "max_blocks": limit},
        )
    return {
        "id": str(brief.get("id") or f"bb-{uuid.uuid4().hex[:10]}"),
        "title": str(brief.get("title") or "建築意圖").strip() or "建築意圖",
        "region": region,
        "location": location,
        "style": style,
        "prompt": prompt,
        "block_count": block_count,
        "notes": str(brief.get("notes") or "").strip(),
        "status": str(brief.get("status") or "pending_builder"),
        "source": str(brief.get("source") or "narrative_workspace"),
    }


def get_build_brief(brief_id: str) -> dict[str, Any]:
    for item in list_entities("build_briefs"):
        if str(item.get("id")) == brief_id:
            return item
    raise BuildBriefError(f"build_brief 不存在：{brief_id}", code="not_found")


def list_build_briefs() -> list[dict[str, Any]]:
    return list_entities("build_briefs")


def _schematic_material_to_mcp(name: str) -> str:
    return mcp.normalize_material(block_key(name))


def compute_placement_bounds(schematic: Schematic, anchor: tuple[int, int, int]) -> dict[str, Any]:
    ax, ay, az = anchor
    solid = schematic.solid_count()
    return {
        "anchor": {"x": ax, "y": ay, "z": az},
        "width": schematic.width,
        "height": schematic.height,
        "length": schematic.length,
        "world_min": {"x": ax, "y": ay, "z": az},
        "world_max": {
            "x": ax + schematic.width - 1,
            "y": ay + schematic.height - 1,
            "z": az + schematic.length - 1,
        },
        "solid_count": solid,
        "volume": schematic.volume(),
    }


def _assert_placement_safe(schematic: Schematic, anchor: tuple[int, int, int]) -> dict[str, Any]:
    bounds = compute_placement_bounds(schematic, anchor)
    limit = _max_blocks()
    if schematic.width > MAX_AXIS or schematic.height > MAX_AXIS or schematic.length > MAX_AXIS:
        raise BuildBriefError(
            f"schematic 單軸不得超過 {MAX_AXIS} 格",
            code="bounds_exceeded",
            extra=bounds,
        )
    if bounds["solid_count"] > limit:
        raise BuildBriefError(
            f"實心方塊 {bounds['solid_count']} 超過單次上限 {limit}",
            code="block_limit",
            extra=bounds,
        )
    if bounds["solid_count"] <= 0:
        raise BuildBriefError("schematic 沒有可放置的方塊", code="empty_schematic")
    return bounds


def _generate_building_from_brief(brief: dict[str, Any]) -> tuple[dict[str, Any], Schematic]:
    """沿用 /buildings/generate 路徑：校驗 → LLM／程序化 schematic。"""
    try:
        invoked = invoke_tool(
            TOOL_BUILDER_GENERATE,
            {
                "prompt": brief["prompt"],
                "style": brief["style"],
                "location": brief["location"],
                "region": brief["region"],
                "block_count": brief["block_count"],
            },
        )
    except ToolValidationError as exc:
        raise BuildBriefError(str(exc), code=exc.code, extra=exc.extra) from exc
    params = invoked["params"]
    base = {
        "id": f"bld-{uuid.uuid4().hex[:10]}",
        **params,
        "status": "planned",
        "build_brief_id": brief["id"],
        "note": f"由 build_brief {brief['id']} 生成。",
    }
    designed = generate_llm_structure(
        prompt=str(params.get("prompt") or ""),
        style=str(params.get("style") or ""),
        block_count=int(params.get("block_count") or 64),
        seed=base["id"],
        region=str(params.get("region") or ""),
    )
    if designed is not None:
        model, design_payload = designed
        building = attach_model(base, model, generator="llm", design=design_payload)
    else:
        building = attach_schematic(base)
    stored = upsert_entity("buildings", building)
    get_store().upsert(
        COL_WORLDVIEW,
        f"建筑方案（build_brief）：{params['style']} @ {params['location']}\n{params['prompt']}",
        {"kind": "building", "building_id": stored["id"], "build_brief_id": brief["id"]},
        skip_quality=True,
    )
    _, model = ensure_schematic(stored)
    return stored, model


def _bridge_status_for_apply(dry_run: bool) -> dict[str, Any]:
    status = monitor_status()
    if dry_run or status.get("dry_run"):
        return status
    if not status.get("enabled"):
        raise BuildBriefError(
            "MineMCP 未啟用（設定 EVOL_MC_MCP_ENABLED=true）",
            code="bridge_disabled",
            extra={"bridge": status},
        )
    if not status.get("connected"):
        raise BuildBriefError(
            "MineMCP 橋接未連線，請確認伺服器與 Token 後再落地建築",
            code="bridge_offline",
            extra={"bridge": status, "probe": status.get("probe") or {}},
        )
    return status


def place_schematic_blocks(
    schematic: Schematic,
    anchor: tuple[int, int, int],
    *,
    dry_run: bool = False,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """以 place_block 逐格落地 schematic（經 execute_named_tool 護欄）。"""
    bounds = _assert_placement_safe(schematic, anchor)
    ax, ay, az = anchor
    total = bounds["solid_count"]
    connector_dry = mcp.load_config().dry_run

    if dry_run:
        if on_progress:
            on_progress(0, total)
        return {
            "ok": True,
            "dry_run": True,
            "cancelled": False,
            "blocks_total": total,
            "blocks_placed": 0,
            "blocks_failed": 0,
            "bounds": bounds,
            "errors": [],
            "note": "預覽模式：未呼叫 MineMCP",
        }

    placed = 0
    failed = 0
    errors: list[str] = []
    cancelled = False

    for lx, ly, lz, name in schematic.iter_solid():
        if cancel_check and cancel_check():
            cancelled = True
            break
        wx, wy, wz = ax + lx, ay + ly, az + lz
        material = _schematic_material_to_mcp(name)
        try:
            result = execute_named_tool(
                mcp.PLACE_BLOCK,
                {"x": wx, "y": wy, "z": wz, "material": material},
            )
        except ToolValidationError as exc:
            failed += 1
            errors.append(str(exc))
            continue
        if result.get("ok"):
            placed += 1
        else:
            failed += 1
            errors.append(str(result.get("error") or "place_block failed"))
        if on_progress:
            on_progress(placed + failed, total)

    return {
        "ok": failed == 0 and not cancelled,
        "dry_run": connector_dry,
        "cancelled": cancelled,
        "blocks_total": total,
        "blocks_placed": placed,
        "blocks_failed": failed,
        "bounds": bounds,
        "errors": errors[:20],
    }


def preview_build_brief(brief: dict[str, Any], *, generate: bool = True) -> dict[str, Any]:
    """Dry-run：估算方塊數與世界座標邊界，可選生成 schematic。"""
    normalized = validate_build_brief(brief)
    anchor = mcp.parse_xyz(normalized["location"])
    if anchor is None:
        raise BuildBriefError("location 無法解析", code="invalid_location")

    if generate:
        building, schematic = _generate_building_from_brief(normalized)
        bounds = _assert_placement_safe(schematic, anchor)
        preview = preview_payload(schematic, building_id=str(building.get("id") or ""))
    else:
        building = None
        schematic = None
        bounds = {
            "anchor": {"x": anchor[0], "y": anchor[1], "z": anchor[2]},
            "solid_count": normalized["block_count"],
            "estimate_only": True,
        }
        preview = None

    bridge = monitor_status()
    return {
        "brief": normalized,
        "building": building,
        "bounds": bounds,
        "preview": preview,
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
        },
        "dry_run": True,
    }


def apply_build_brief(
    brief: dict[str, Any],
    *,
    dry_run: bool = False,
    generate: bool = True,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """落地建築：生成 schematic 並 place_block。需使用者明確觸發（API 層責任）。"""
    normalized = validate_build_brief(brief)
    bridge = _bridge_status_for_apply(dry_run)

    anchor = mcp.parse_xyz(normalized["location"])
    if anchor is None:
        raise BuildBriefError("location 無法解析", code="invalid_location")

    if generate or not normalized.get("building_id"):
        building, schematic = _generate_building_from_brief(normalized)
    else:
        resolved: dict[str, Any] | None = None
        for candidate in list_entities("buildings"):
            if str(candidate.get("id")) == normalized["building_id"]:
                resolved = candidate
                break
        if resolved is None:
            raise BuildBriefError("關聯 building 不存在", code="building_not_found")
        building, schematic = ensure_schematic(resolved)

    assert building is not None

    placement = place_schematic_blocks(
        schematic,
        anchor,
        dry_run=dry_run,
        cancel_check=cancel_check,
        on_progress=on_progress,
    )

    try:
        stored_brief = get_build_brief(normalized["id"])
    except BuildBriefError:
        stored_brief = normalized

    status = "built" if placement.get("ok") else ("cancelled" if placement.get("cancelled") else "build_failed")
    updated_brief = upsert_entity(
        "build_briefs",
        {
            **stored_brief,
            **normalized,
            "status": status,
            "building_id": building.get("id"),
            "build_job": {
                "blocks_total": placement["blocks_total"],
                "blocks_placed": placement["blocks_placed"],
                "blocks_failed": placement["blocks_failed"],
                "dry_run": placement.get("dry_run"),
                "cancelled": placement.get("cancelled"),
            },
        },
    )
    building_status = "dispatched" if placement.get("ok") else building.get("status")
    upsert_entity(
        "buildings",
        {
            **building,
            "status": building_status,
            "mcp": {
                "ok": placement.get("ok"),
                "dry_run": placement.get("dry_run"),
                "blocks_placed": placement["blocks_placed"],
                "blocks_total": placement["blocks_total"],
            },
        },
    )
    get_store().upsert(
        COL_EVENTS,
        f"build_brief 落地 {normalized['id']} → {placement['blocks_placed']}/{placement['blocks_total']} 方塊",
        {"kind": "minecraft", "build_brief_id": normalized["id"], "building_id": building.get("id")},
        skip_quality=True,
    )
    return {
        "brief": updated_brief,
        "building": building,
        "placement": placement,
        "bridge": bridge,
        "dry_run": dry_run,
    }


def get_job(job_id: str) -> BuildJob:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise BuildBriefError(f"job 不存在：{job_id}", code="job_not_found")
    return job


def cancel_job(job_id: str) -> BuildJob:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise BuildBriefError(f"job 不存在：{job_id}", code="job_not_found")
        job.cancel_requested = True
    return job


def start_apply_job(brief: dict[str, Any], *, dry_run: bool = False) -> BuildJob:
    normalized = validate_build_brief(brief)
    job = BuildJob(job_id=f"bbjob-{uuid.uuid4().hex[:10]}", brief_id=normalized["id"], dry_run=dry_run)
    with _jobs_lock:
        _jobs[job.job_id] = job

    def _run() -> None:
        job.status = "running"
        try:

            def _progress(done: int, total: int) -> None:
                job.blocks_placed = done
                job.blocks_total = total

            result = apply_build_brief(
                normalized,
                dry_run=dry_run,
                cancel_check=lambda: job.cancel_requested,
                on_progress=_progress,
            )
            job.result = result
            job.blocks_placed = result["placement"]["blocks_placed"]
            job.blocks_total = result["placement"]["blocks_total"]
            job.blocks_failed = result["placement"]["blocks_failed"]
            job.status = "cancelled" if result["placement"].get("cancelled") else (
                "completed" if result["placement"].get("ok") else "failed"
            )
        except BuildBriefError as exc:
            job.status = "failed"
            job.error = str(exc)
            job.result = {"code": exc.code, "extra": exc.extra}
        except (ToolValidationError, SchematicError) as exc:
            job.status = "failed"
            job.error = str(exc)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return job


def job_to_dict(job: BuildJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "brief_id": job.brief_id,
        "status": job.status,
        "dry_run": job.dry_run,
        "blocks_total": job.blocks_total,
        "blocks_placed": job.blocks_placed,
        "blocks_failed": job.blocks_failed,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result": job.result if job.status in {"completed", "failed", "cancelled"} else None,
    }
