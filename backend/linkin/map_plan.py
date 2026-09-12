"""Phase 4 區域地圖計畫：從敘事上下文生成結構化佈局，預覽與 MineMCP 落地。

Schema version 1 — 見 ``MAP_PLAN_SCHEMA_DOC`` 與 ``validate_map_plan``。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import uuid
from typing import Any

from backend.linkin.constitution import allowed_styles_for_region
from backend.linkin.knowledge import COL_NPCS, get_store, list_entities
from backend.linkin.minecraft import STYLE_MATERIALS
from backend.linkin.tools import ToolValidationError
from backend.tools import minecraft_mcp as mcp

logger = logging.getLogger(__name__)

MAP_PLAN_VERSION = 1
MAX_PLOTS = 32
MAX_ESTIMATED_BLOCKS = 2000
MAX_AXIS_SPAN = 128
PLOT_KINDS = frozenset({"marker", "poi", "path", "terrain"})

MAP_PLAN_SCHEMA_DOC = """
map_plan v1 必填欄位：
- version (int, 固定 1)
- id (str)
- title (str)
- region (str)
- seed (str)
- origin ({x,y,z} 整數)
- bounds ({x1,y1,z1,x2,y2,z2} 整數，各軸跨度 ≤ MAX_AXIS_SPAN)
- plots (array, len ≤ MAX_PLOTS)
  - id, kind ∈ marker|poi|path|terrain, title
  - marker/poi: location {x,y,z}, material (str), 可選 style / link
  - path: points [{x,y,z},...] (≥2), width (int≥1), material
  - terrain: geometry {type:"fill", x1..z2, material} 相對 origin 或絕對座標
- landmarks (array, 可選): id, title, location, notes
- summary (str, 可選)
- source (llm|fallback|manual, 可選)
"""


class MapPlanError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_plan"):
        super().__init__(message)
        self.code = code


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MapPlanError(f"{field} 必須為整數", code="invalid_field") from exc


def _parse_location(value: Any, *, field: str = "location") -> dict[str, int]:
    if isinstance(value, dict):
        return {"x": _as_int(value.get("x"), f"{field}.x"), "y": _as_int(value.get("y"), f"{field}.y"), "z": _as_int(value.get("z"), f"{field}.z")}
    xyz = mcp.parse_xyz(value)
    if xyz is None:
        raise MapPlanError(f"{field} 無法解析為 x,y,z", code="invalid_field")
    return {"x": xyz[0], "y": xyz[1], "z": xyz[2]}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_ready() -> bool:
    if os.getenv("EVOL_LINKIN_NO_LLM", "").strip().lower() in {"1", "true", "yes"}:
        return False
    try:
        from backend.core.llm_config import get_runtime_config

        cfg = get_runtime_config()
        key = str(cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    except Exception:
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")


def _axis_span(bounds: dict[str, int]) -> tuple[int, int, int]:
    return (
        abs(bounds["x2"] - bounds["x1"]),
        abs(bounds["y2"] - bounds["y1"]),
        abs(bounds["z2"] - bounds["z1"]),
    )


def _normalize_bounds(bounds: dict[str, Any]) -> dict[str, int]:
    x1 = _as_int(bounds.get("x1"), "bounds.x1")
    y1 = _as_int(bounds.get("y1"), "bounds.y1")
    z1 = _as_int(bounds.get("z1"), "bounds.z1")
    x2 = _as_int(bounds.get("x2"), "bounds.x2")
    y2 = _as_int(bounds.get("y2"), "bounds.y2")
    z2 = _as_int(bounds.get("z2"), "bounds.z2")
    return {
        "x1": min(x1, x2),
        "y1": min(y1, y2),
        "z1": min(z1, z2),
        "x2": max(x1, x2),
        "y2": max(y1, y2),
        "z2": max(z1, z2),
    }


def _estimate_plot_blocks(plot: dict[str, Any]) -> int:
    kind = str(plot.get("kind") or "")
    if kind in {"marker", "poi"}:
        return 1
    if kind == "path":
        points = plot.get("points") or []
        width = max(1, int(plot.get("width") or 1))
        if len(points) < 2:
            return 0
        total = 0
        for i in range(len(points) - 1):
            a = _parse_location(points[i], field=f"points[{i}]")
            b = _parse_location(points[i + 1], field=f"points[{i + 1}]")
            dx = abs(b["x"] - a["x"])
            dy = abs(b["y"] - a["y"])
            dz = abs(b["z"] - a["z"])
            total += max(dx, dy, dz, 1) * width
        return total
    if kind == "terrain":
        geom = plot.get("geometry") or {}
        if str(geom.get("type") or "fill") != "fill":
            return 0
        vol = mcp.fill_volume(
            _as_int(geom.get("x1"), "geometry.x1"),
            _as_int(geom.get("y1"), "geometry.y1"),
            _as_int(geom.get("z1"), "geometry.z1"),
            _as_int(geom.get("x2"), "geometry.x2"),
            _as_int(geom.get("y2"), "geometry.y2"),
            _as_int(geom.get("z2"), "geometry.z2"),
        )
        return max(vol, 0)
    return 0


def validate_map_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """驗證並正規化 map_plan v1；超限則 raise MapPlanError。"""
    if not isinstance(plan, dict):
        raise MapPlanError("map_plan 必須為 JSON 物件")
    version = _as_int(plan.get("version", MAP_PLAN_VERSION), "version")
    if version != MAP_PLAN_VERSION:
        raise MapPlanError(f"不支援的 map_plan 版本：{version}", code="unsupported_version")

    plots_raw = plan.get("plots")
    if not isinstance(plots_raw, list) or not plots_raw:
        raise MapPlanError("plots 必須為非空陣列", code="invalid_plots")
    if len(plots_raw) > MAX_PLOTS:
        raise MapPlanError(f"plots 不得超過 {MAX_PLOTS} 個（收到 {len(plots_raw)}）", code="plot_limit")

    origin = _parse_location(plan.get("origin") or {"x": 0, "y": 64, "z": 0}, field="origin")
    bounds = _normalize_bounds(plan.get("bounds") or {"x1": -32, "y1": 60, "z1": -32, "x2": 32, "y2": 72, "z2": 32})
    span_x, span_y, span_z = _axis_span(bounds)
    if max(span_x, span_y, span_z) > MAX_AXIS_SPAN:
        raise MapPlanError(
            f"bounds 各軸跨度不得超過 {MAX_AXIS_SPAN}（收到 x={span_x} y={span_y} z={span_z}）",
            code="axis_limit",
        )

    normalized_plots: list[dict[str, Any]] = []
    estimated_blocks = 0
    for idx, raw_plot in enumerate(plots_raw):
        if not isinstance(raw_plot, dict):
            raise MapPlanError(f"plots[{idx}] 必須為物件", code="invalid_plot")
        kind = str(raw_plot.get("kind") or "poi").strip().lower()
        if kind not in PLOT_KINDS:
            raise MapPlanError(f"plots[{idx}].kind 無效：{kind}", code="invalid_plot")
        plot_id = str(raw_plot.get("id") or f"plot-{idx + 1}")
        title = str(raw_plot.get("title") or plot_id).strip() or plot_id
        entry: dict[str, Any] = {"id": plot_id, "kind": kind, "title": title}
        if raw_plot.get("link"):
            entry["link"] = dict(raw_plot["link"])
        if raw_plot.get("style"):
            entry["style"] = str(raw_plot["style"])

        if kind in {"marker", "poi"}:
            loc = _parse_location(raw_plot.get("location") or origin, field=f"plots[{idx}].location")
            material = mcp.normalize_material(str(raw_plot.get("material") or STYLE_MATERIALS.get(str(raw_plot.get("style") or ""), "GOLD_BLOCK")))
            entry["location"] = loc
            entry["material"] = material
        elif kind == "path":
            points_raw = raw_plot.get("points") or []
            if not isinstance(points_raw, list) or len(points_raw) < 2:
                raise MapPlanError(f"plots[{idx}] path 需要至少 2 個 points", code="invalid_plot")
            points = [_parse_location(p, field=f"plots[{idx}].points") for p in points_raw]
            width = max(1, _as_int(raw_plot.get("width") or 1, f"plots[{idx}].width"))
            material = mcp.normalize_material(str(raw_plot.get("material") or "GRAVEL"))
            entry["points"] = points
            entry["width"] = width
            entry["material"] = material
        elif kind == "terrain":
            geom = dict(raw_plot.get("geometry") or {})
            if str(geom.get("type") or "fill") != "fill":
                raise MapPlanError(f"plots[{idx}] terrain 僅支援 geometry.type=fill", code="invalid_plot")
            fill = {
                "type": "fill",
                "x1": _as_int(geom.get("x1"), f"plots[{idx}].geometry.x1"),
                "y1": _as_int(geom.get("y1"), f"plots[{idx}].geometry.y1"),
                "z1": _as_int(geom.get("z1"), f"plots[{idx}].geometry.z1"),
                "x2": _as_int(geom.get("x2"), f"plots[{idx}].geometry.x2"),
                "y2": _as_int(geom.get("y2"), f"plots[{idx}].geometry.y2"),
                "z2": _as_int(geom.get("z2"), f"plots[{idx}].geometry.z2"),
                "material": mcp.normalize_material(str(geom.get("material") or "GRASS_BLOCK")),
            }
            entry["geometry"] = fill

        block_est = _estimate_plot_blocks(entry)
        estimated_blocks += block_est
        normalized_plots.append(entry)

    if estimated_blocks > MAX_ESTIMATED_BLOCKS:
        raise MapPlanError(
            f"預估方塊數 {estimated_blocks} 超過上限 {MAX_ESTIMATED_BLOCKS}",
            code="block_limit",
        )

    landmarks: list[dict[str, Any]] = []
    for idx, lm in enumerate(plan.get("landmarks") or []):
        if not isinstance(lm, dict):
            continue
        landmarks.append(
            {
                "id": str(lm.get("id") or f"lm-{idx + 1}"),
                "title": str(lm.get("title") or f"landmark-{idx + 1}"),
                "location": _parse_location(lm.get("location") or origin, field=f"landmarks[{idx}].location"),
                "notes": str(lm.get("notes") or ""),
            }
        )

    region = str(plan.get("region") or "织庭都").strip() or "织庭都"
    allowed = allowed_styles_for_region(region)
    for plot in normalized_plots:
        style = plot.get("style")
        if style:
            resolved = _resolve_region_style(region, str(style))
            if allowed and resolved not in allowed:
                raise MapPlanError(
                    f"plot「{plot['title']}」style「{style}」與區域「{region}」不符",
                    code="style_mismatch",
                )
            plot["style"] = resolved

    normalized = {
        "version": MAP_PLAN_VERSION,
        "id": str(plan.get("id") or f"map-{uuid.uuid4().hex[:10]}"),
        "title": str(plan.get("title") or f"{region}區域佈局").strip() or f"{region}區域佈局",
        "region": region,
        "seed": str(plan.get("seed") or uuid.uuid4().hex[:8]),
        "origin": origin,
        "bounds": bounds,
        "plots": normalized_plots,
        "landmarks": landmarks,
        "summary": str(plan.get("summary") or "").strip(),
        "source": str(plan.get("source") or "manual"),
        "estimated_blocks": estimated_blocks,
    }
    return normalized


def preview_map_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """預覽摘要：邊界、plot 數、預估方塊、POI 列表。不寫世界。"""
    validated = validate_map_plan(plan)
    pois: list[dict[str, Any]] = []
    for plot in validated["plots"]:
        if plot["kind"] in {"marker", "poi"}:
            loc = plot["location"]
            pois.append(
                {
                    "id": plot["id"],
                    "title": plot["title"],
                    "kind": plot["kind"],
                    "location": f"{loc['x']},{loc['y']},{loc['z']}",
                    "material": plot.get("material"),
                    "link": plot.get("link"),
                }
            )
    for lm in validated.get("landmarks") or []:
        loc = lm["location"]
        pois.append(
            {
                "id": lm["id"],
                "title": lm["title"],
                "kind": "landmark",
                "location": f"{loc['x']},{loc['y']},{loc['z']}",
                "notes": lm.get("notes"),
            }
        )
    span_x, span_y, span_z = _axis_span(validated["bounds"])
    return {
        "plan_id": validated["id"],
        "title": validated["title"],
        "region": validated["region"],
        "bounds": validated["bounds"],
        "axis_span": {"x": span_x, "y": span_y, "z": span_z},
        "plot_count": len(validated["plots"]),
        "estimated_blocks": validated["estimated_blocks"],
        "pois": pois,
        "paths": [p["id"] for p in validated["plots"] if p["kind"] == "path"],
        "terrain_patches": [p["id"] for p in validated["plots"] if p["kind"] == "terrain"],
    }


def _seed_int(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _resolve_region_style(region: str, style: str | None) -> str:
    allowed = allowed_styles_for_region(region) or ["契约广场"]
    raw = str(style or allowed[0]).strip()
    if raw in allowed:
        return raw
    faction_aliases = {"织庭盟", "自由舟", "宁渊庭", "loom_order", "free_arks", "stilldeep"}
    if raw in faction_aliases:
        return allowed[0]
    return allowed[0]


def _offset_from_seed(seed: str, index: int, radius: int = 24) -> tuple[int, int]:
    base = _seed_int(f"{seed}:{index}")
    angle = (base % 360) * math.pi / 180.0
    dist = 8 + (base % max(radius - 8, 1))
    return int(round(math.cos(angle) * dist)), int(round(math.sin(angle) * dist))


def gather_narrative_context(
    *,
    workspace_drafts: dict[str, Any] | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """從工作區草稿或已提交實體彙整生成上下文。"""
    drafts = dict(workspace_drafts or {})
    region_name = str(region or (drafts.get("story_arc") or {}).get("region") or "织庭都").strip() or "织庭都"

    story_arc = drafts.get("story_arc") if isinstance(drafts.get("story_arc"), dict) else None
    npc = drafts.get("npc") if isinstance(drafts.get("npc"), dict) else None
    build_brief = drafts.get("build_brief") if isinstance(drafts.get("build_brief"), dict) else None
    quest = drafts.get("quest") if isinstance(drafts.get("quest"), dict) else None

    committed_arcs = [a for a in list_entities("story_arcs") if str(a.get("region") or "") == region_name]
    committed_briefs = [b for b in list_entities("build_briefs") if str(b.get("region") or "") == region_name]
    committed_npcs: list[dict[str, Any]] = []
    try:
        for rec in get_store().list(COL_NPCS):
            meta = dict(rec.get("metadata") or {})
            loc = str(meta.get("location") or "")
            if region_name in loc or loc == region_name:
                committed_npcs.append(
                    {
                        "name": meta.get("name") or "",
                        "location": loc,
                        "faction": meta.get("faction") or "",
                        "occupation": meta.get("occupation") or "",
                    }
                )
    except Exception:
        committed_npcs = []

    if not story_arc and committed_arcs:
        story_arc = committed_arcs[-1]
    if not build_brief and committed_briefs:
        build_brief = committed_briefs[-1]
    if not npc and committed_npcs:
        npc = committed_npcs[0]

    return {
        "region": region_name,
        "story_arc": story_arc,
        "quest": quest,
        "npc": npc,
        "build_brief": build_brief,
        "npcs": committed_npcs[:8],
        "build_briefs": committed_briefs[:8],
    }


def fallback_map_plan(
    *,
    context: dict[str, Any],
    seed: str,
    origin: dict[str, int] | None = None,
) -> dict[str, Any]:
    """無 LLM 時的確定性區域佈局。"""
    region = str(context.get("region") or "织庭都")
    story = context.get("story_arc") or {}
    brief = context.get("build_brief") or {}
    npc = context.get("npc") or {}
    ox, oy, oz = (origin or {"x": 0, "y": 64, "z": 0}).values()

    hub_loc = _parse_location(brief.get("location") or f"{ox},{oy},{oz}", field="build_brief.location")
    style = _resolve_region_style(region, str(brief.get("style") or ""))
    hub_material = STYLE_MATERIALS.get(style, "GOLD_BLOCK")

    plots: list[dict[str, Any]] = [
        {
            "id": "plot-hub",
            "kind": "poi",
            "title": str(brief.get("title") or story.get("title") or f"{region}樞紐"),
            "location": hub_loc,
            "material": hub_material,
            "style": style,
            "link": {"build_brief_title": brief.get("title"), "role": "hub"},
        }
    ]

    npcs = list(context.get("npcs") or [])
    if npc and not npcs:
        npcs = [npc]
    for idx, npc_row in enumerate(npcs[:6]):
        dx, dz = _offset_from_seed(seed, idx + 1)
        plots.append(
            {
                "id": f"plot-npc-{idx + 1}",
                "kind": "marker",
                "title": str(npc_row.get("name") or f"NPC-{idx + 1}"),
                "location": {"x": hub_loc["x"] + dx, "y": hub_loc["y"], "z": hub_loc["z"] + dz},
                "material": "EMERALD_BLOCK",
                "link": {"npc_name": npc_row.get("name"), "role": "npc"},
            }
        )
        plots.append(
            {
                "id": f"plot-path-{idx + 1}",
                "kind": "path",
                "title": f"徑道→{npc_row.get('name') or idx + 1}",
                "points": [hub_loc, {"x": hub_loc["x"] + dx, "y": hub_loc["y"], "z": hub_loc["z"] + dz}],
                "width": 1,
                "material": "GRAVEL",
            }
        )

    pad = 6
    plots.append(
        {
            "id": "plot-terrain-hub",
            "kind": "terrain",
            "title": "樞紐平台",
            "geometry": {
                "type": "fill",
                "x1": hub_loc["x"] - pad,
                "y1": hub_loc["y"] - 1,
                "z1": hub_loc["z"] - pad,
                "x2": hub_loc["x"] + pad,
                "y2": hub_loc["y"] - 1,
                "z2": hub_loc["z"] + pad,
                "material": "GRASS_BLOCK",
            },
        }
    )

    xs = [hub_loc["x"]]
    zs = [hub_loc["z"]]
    for p in plots:
        if p["kind"] in {"marker", "poi"}:
            loc = p["location"]
            xs.append(loc["x"])
            zs.append(loc["z"])
        elif p["kind"] == "path":
            for pt in p["points"]:
                xs.append(pt["x"])
                zs.append(pt["z"])

    margin = 8
    bounds = {
        "x1": min(xs) - margin,
        "y1": hub_loc["y"] - 2,
        "z1": min(zs) - margin,
        "x2": max(xs) + margin,
        "y2": hub_loc["y"] + 4,
        "z2": max(zs) + margin,
    }

    title = str(story.get("title") or brief.get("title") or f"{region}區域佈局")
    summary = str(story.get("summary") or f"以 {brief.get('title') or '樞紐'} 為中心，串連 {len(npcs)} 個 NPC 標記與徑道。")

    plan = {
        "version": MAP_PLAN_VERSION,
        "id": f"map-{uuid.uuid4().hex[:10]}",
        "title": title,
        "region": region,
        "seed": seed,
        "origin": {"x": ox, "y": oy, "z": oz},
        "bounds": bounds,
        "summary": summary,
        "source": "fallback",
        "plots": plots,
        "landmarks": [
            {
                "id": "lm-hub",
                "title": str(brief.get("title") or "樞紐"),
                "location": hub_loc,
                "notes": str(brief.get("prompt") or brief.get("notes") or ""),
            }
        ],
    }
    return validate_map_plan(plan)


def generate_map_plan(
    *,
    context: dict[str, Any],
    seed: str,
    origin: dict[str, int] | None = None,
) -> dict[str, Any]:
    """嘗試 LLM 生成 map_plan；失敗則 fallback_map_plan。"""
    region = str(context.get("region") or "织庭都")
    seed = (seed or uuid.uuid4().hex[:8]).strip() or uuid.uuid4().hex[:8]
    if not _llm_ready():
        plan = fallback_map_plan(context=context, seed=seed, origin=origin)
        return {"plan": plan, "source": "fallback"}

    try:
        from backend.core.llm import call_llm

        try:
            from backend.linkin.prompts import inherit_prompt

            system = inherit_prompt("narrative_director")
        except Exception:
            system = "你是靈境·Linkin 區域規劃師。輸出須符合世界觀，禁止現實政治與寫實暴力。"

        ctx_json = json.dumps(
            {
                "region": region,
                "story_arc": context.get("story_arc"),
                "quest": context.get("quest"),
                "npc": context.get("npc"),
                "build_brief": context.get("build_brief"),
                "npcs": context.get("npcs"),
                "build_briefs": context.get("build_briefs"),
            },
            ensure_ascii=False,
        )
        prompt = (
            "為 Minecraft RPG Phase 4 生成區域 map_plan JSON（version=1）。只輸出 JSON 物件。\n"
            "必填：version, title, region, seed, origin{x,y,z}, bounds{x1..z2}, plots[], 可選 landmarks[], summary。\n"
            "plots 元素：id, kind(marker|poi|path|terrain), title；"
            "marker/poi 含 location 與 material；path 含 points[] 與 width；"
            "terrain 含 geometry{type:fill,x1..z2,material}。\n"
            "POI 需對齊 NPC 與 build_brief 位置意圖；paths 連接樞紐與 POI；terrain 為小型平台。\n"
            f"seed={seed}\n"
            f"上下文：{ctx_json}\n"
            f"硬限制：plots≤{MAX_PLOTS}，預估方塊≤{MAX_ESTIMATED_BLOCKS}，各軸跨度≤{MAX_AXIS_SPAN}。\n"
        )
        raw = (call_llm(prompt, system=system, trace_label="map_generate") or "").strip()
        parsed = _extract_json_object(raw)
        if parsed:
            parsed.setdefault("version", MAP_PLAN_VERSION)
            parsed.setdefault("region", region)
            parsed.setdefault("seed", seed)
            if origin:
                parsed.setdefault("origin", origin)
            plan = validate_map_plan(parsed)
            plan["source"] = "llm"
            return {"plan": plan, "source": "llm"}
    except MapPlanError:
        logger.warning("LLM map_plan 未通過 schema 驗證，改用 fallback", exc_info=True)
    except Exception:
        logger.warning("LLM map_plan 失敗，改用 fallback", exc_info=True)

    plan = fallback_map_plan(context=context, seed=seed, origin=origin)
    return {"plan": plan, "source": "fallback"}


def _iter_path_cells(a: dict[str, int], b: dict[str, int]) -> list[tuple[int, int, int]]:
    x0, y0, z0 = a["x"], a["y"], a["z"]
    x1, y1, z1 = b["x"], b["y"], b["z"]
    steps = max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), 1)
    cells: list[tuple[int, int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        cells.append(
            (
                int(round(x0 + (x1 - x0) * t)),
                int(round(y0 + (y1 - y0) * t)),
                int(round(z0 + (z1 - z0) * t)),
            )
        )
    deduped: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for cell in cells:
        if cell not in seen:
            seen.add(cell)
            deduped.append(cell)
    return deduped


def apply_map_plan(plan: dict[str, Any], *, confirmed: bool = False) -> dict[str, Any]:
    """經 MineMCP 落地 markers/paths/terrain。需 confirm=true；bridge 關閉時 dry-run。"""
    from backend.linkin.minecraft import dispatch_map_plan

    validated = validate_map_plan(plan)
    if not confirmed:
        raise ToolValidationError(
            "地圖落地需 confirm=true",
            code="needs_confirmation",
            extra={"needs_confirmation": True, "plan_id": validated["id"]},
        )
    return dispatch_map_plan(validated, confirmed=True)


__all__ = [
    "MAP_PLAN_SCHEMA_DOC",
    "MAP_PLAN_VERSION",
    "MAX_AXIS_SPAN",
    "MAX_ESTIMATED_BLOCKS",
    "MAX_PLOTS",
    "MapPlanError",
    "apply_map_plan",
    "fallback_map_plan",
    "gather_narrative_context",
    "generate_map_plan",
    "preview_map_plan",
    "validate_map_plan",
]
