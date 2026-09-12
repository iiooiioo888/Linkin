"""Native 2D layout preview — normalize map_plan, build briefs, and world intents for canvas.

When map_plan plots lack absolute coordinates, deterministic offsets from seed/index
are applied so structure remains visible without MineMCP or third-party maps.
"""

from __future__ import annotations

import math
import time
from typing import Any

from backend.linkin.knowledge import COL_NPCS, get_store, list_entities
from backend.linkin.map_plan import MapPlanError, validate_map_plan
from backend.tools import minecraft_mcp as mcp

KIND_COLORS: dict[str, str] = {
    "poi": "#c9a961",
    "marker": "#34c759",
    "path": "#8a8f98",
    "terrain": "#3a3a3c",
    "landmark": "#ffd60a",
    "build_brief": "#64d2ff",
    "npc_intent": "#30d158",
    "quest_intent": "#bf5af2",
    "item_intent": "#5ac8fa",
}

LEGEND_ITEMS: list[dict[str, str]] = [
    {"kind": "poi", "label": "POI / 樞紐", "color": KIND_COLORS["poi"]},
    {"kind": "marker", "label": "標記", "color": KIND_COLORS["marker"]},
    {"kind": "path", "label": "徑道", "color": KIND_COLORS["path"]},
    {"kind": "terrain", "label": "地形", "color": KIND_COLORS["terrain"]},
    {"kind": "landmark", "label": "地標", "color": KIND_COLORS["landmark"]},
    {"kind": "build_brief", "label": "建築意圖（預估）", "color": KIND_COLORS["build_brief"]},
    {"kind": "npc_intent", "label": "NPC 待落地", "color": KIND_COLORS["npc_intent"]},
]


def _offset_from_seed(seed: str, index: int, radius: int = 24) -> tuple[int, int]:
    from backend.linkin.map_plan import _offset_from_seed as map_offset

    return map_offset(seed, index, radius)


def _parse_xyz(raw: Any) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        try:
            return int(raw["x"]), int(raw["y"]), int(raw["z"])
        except (KeyError, TypeError, ValueError):
            return None
    return mcp.parse_xyz(raw)


def _footprint_radius(block_count: int) -> int:
    """Estimate half-width of a square footprint from block count."""
    side = max(4, min(32, int(math.ceil(math.sqrt(max(block_count, 1))))))
    return max(2, side // 2)


def _status_label(status: str | None, *, dry_run: bool = True) -> str:
    raw = str(status or "planned")
    if dry_run and raw not in {"applied", "partial"}:
        return "planned"
    return raw


def _rect_feature(
    *,
    feature_id: str,
    kind: str,
    title: str,
    x1: int,
    z1: int,
    x2: int,
    z2: int,
    status: str,
    source: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "type": "rect",
        "kind": kind,
        "title": title,
        "status": status,
        "label": _status_label(status),
        "source": source,
        "color": KIND_COLORS.get(kind, "#8a8f98"),
        "rect": {"x1": x1, "z1": z1, "x2": x2, "z2": z2},
        "meta": dict(meta or {}),
    }


def _point_feature(
    *,
    feature_id: str,
    kind: str,
    title: str,
    x: int,
    z: int,
    status: str,
    source: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "type": "point",
        "kind": kind,
        "title": title,
        "status": status,
        "label": _status_label(status),
        "source": source,
        "color": KIND_COLORS.get(kind, "#8a8f98"),
        "point": {"x": x, "z": z},
        "meta": dict(meta or {}),
    }


def _polyline_feature(
    *,
    feature_id: str,
    kind: str,
    title: str,
    points: list[dict[str, int]],
    width: int,
    status: str,
    source: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "type": "polyline",
        "kind": kind,
        "title": title,
        "status": status,
        "label": _status_label(status),
        "source": source,
        "color": KIND_COLORS.get(kind, "#8a8f98"),
        "polyline": {"points": points, "width": max(1, width)},
        "meta": dict(meta or {}),
    }


def _collect_xz_points(features: list[dict[str, Any]]) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    for feat in features:
        t = feat.get("type")
        if t == "point":
            p = feat.get("point") or {}
            pts.append((int(p["x"]), int(p["z"])))
        elif t == "rect":
            r = feat.get("rect") or {}
            pts.extend(
                [
                    (int(r["x1"]), int(r["z1"])),
                    (int(r["x2"]), int(r["z2"])),
                ]
            )
        elif t == "polyline":
            for p in feat.get("polyline", {}).get("points") or []:
                pts.append((int(p["x"]), int(p["z"])))
    return pts


def _compute_bounds(
    features: list[dict[str, Any]],
    plan_bounds: dict[str, int] | None,
    margin: int = 8,
) -> dict[str, int]:
    xs: list[int] = []
    zs: list[int] = []
    if plan_bounds:
        xs.extend([int(plan_bounds["x1"]), int(plan_bounds["x2"])])
        zs.extend([int(plan_bounds["z1"]), int(plan_bounds["z2"])])
    for x, z in _collect_xz_points(features):
        xs.append(x)
        zs.append(z)
    if not xs:
        return {"x1": -32, "z1": -32, "x2": 32, "z2": 32}
    return {
        "x1": min(xs) - margin,
        "z1": min(zs) - margin,
        "x2": max(xs) + margin,
        "z2": max(zs) + margin,
    }


def normalize_plot_features(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert validated map_plan plots/landmarks into canvas features."""
    validated = validate_map_plan(plan)
    status = str(plan.get("status") or "planned")
    features: list[dict[str, Any]] = []

    for plot in validated["plots"]:
        kind = plot["kind"]
        plot_id = plot["id"]
        title = plot["title"]
        meta = {
            "material": plot.get("material"),
            "estimated_blocks": plot.get("estimated_blocks"),
            "style": plot.get("style"),
            "link": plot.get("link"),
        }
        if kind in {"marker", "poi"}:
            loc = plot["location"]
            x, z = loc["x"], loc["z"]
            meta["layout_mode"] = "absolute"
            features.append(
                _point_feature(
                    feature_id=plot_id,
                    kind=kind,
                    title=title,
                    x=x,
                    z=z,
                    status=status,
                    source="map_plan",
                    meta=meta,
                )
            )
        elif kind == "path":
            raw_points = plot.get("points") or []
            points = [{"x": pt["x"], "z": pt["z"]} for pt in raw_points]
            meta["layout_mode"] = "absolute"
            if len(points) >= 2:
                features.append(
                    _polyline_feature(
                        feature_id=plot_id,
                        kind=kind,
                        title=title,
                        points=points,
                        width=int(plot.get("width") or 1),
                        status=status,
                        source="map_plan",
                        meta=meta,
                    )
                )
        elif kind == "terrain":
            geom = plot.get("geometry") or {}
            x1, z1 = int(geom["x1"]), int(geom["z1"])
            x2, z2 = int(geom["x2"]), int(geom["z2"])
            meta["layout_mode"] = "absolute"
            meta["material"] = geom.get("material")
            features.append(
                _rect_feature(
                    feature_id=plot_id,
                    kind=kind,
                    title=title,
                    x1=min(x1, x2),
                    z1=min(z1, z2),
                    x2=max(x1, x2),
                    z2=max(z1, z2),
                    status=status,
                    source="map_plan",
                    meta=meta,
                )
            )

    for lm in validated.get("landmarks") or []:
        loc = lm["location"]
        features.append(
            _point_feature(
                feature_id=str(lm["id"]),
                kind="landmark",
                title=str(lm["title"]),
                x=loc["x"],
                z=loc["z"],
                status=status,
                source="map_plan",
                meta={"notes": lm.get("notes"), "layout_mode": "absolute"},
            )
        )

    return features


def normalize_build_brief_features(
    briefs: list[dict[str, Any]],
    *,
    seed: str,
    hub: tuple[int, int, int] | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    hub_x, _, hub_z = hub or (0, 64, 0)
    for idx, brief in enumerate(briefs):
        brief_id = str(brief.get("id") or f"bb-{idx}")
        title = str(brief.get("title") or "建築意圖")
        status = str(brief.get("status") or "pending_builder")
        block_count = int(brief.get("block_count") or brief.get("blockCount") or 800)
        radius = _footprint_radius(block_count)
        xyz = _parse_xyz(brief.get("location") or brief.get("coords"))
        layout_mode = "absolute"
        if xyz is None:
            dx, dz = _offset_from_seed(seed, idx + 20, radius=32)
            x, _, z = hub_x + dx, 64, hub_z + dz
            layout_mode = "synthetic"
        else:
            x, _, z = xyz
        features.append(
            _rect_feature(
                feature_id=brief_id,
                kind="build_brief",
                title=title,
                x1=x - radius,
                z1=z - radius,
                x2=x + radius,
                z2=z + radius,
                status=status,
                source="build_brief",
                meta={
                    "block_count": block_count,
                    "region": brief.get("region"),
                    "style": brief.get("style"),
                    "layout_mode": layout_mode,
                    "footprint_estimate": True,
                },
            )
        )
    return features


def normalize_world_intent_features(
    npcs: list[dict[str, Any]],
    *,
    seed: str,
    hub: tuple[int, int, int] | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    hub_x, _, hub_z = hub or (0, 64, 0)
    for idx, npc in enumerate(npcs):
        npc_id = str(npc.get("id") or f"npc-{idx}")
        title = str(npc.get("name") or npc_id)
        status = str(npc.get("world_status") or "pending_world")
        xyz = _parse_xyz(npc.get("coords") or npc.get("location") or npc.get("spawn"))
        layout_mode = "absolute"
        if xyz is None:
            dx, dz = _offset_from_seed(seed, idx + 40, radius=28)
            x, _, z = hub_x + dx, 64, hub_z + dz
            layout_mode = "synthetic"
        else:
            x, _, z = xyz
        features.append(
            _point_feature(
                feature_id=npc_id,
                kind="npc_intent",
                title=title,
                x=x,
                z=z,
                status=status,
                source="world_intent",
                meta={
                    "faction": npc.get("faction"),
                    "occupation": npc.get("occupation"),
                    "layout_mode": layout_mode,
                },
            )
        )
    return features


def _list_npcs_for_region(region: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    region_name = str(region or "").strip()
    try:
        for rec in get_store().list(COL_NPCS):
            meta = dict(rec.get("metadata") or {})
            if rec.get("id"):
                meta.setdefault("id", rec["id"])
            if region_name:
                loc = str(meta.get("location") or "")
                if region_name not in loc and loc != region_name:
                    continue
            rows.append(meta)
    except Exception:
        return []
    return rows


def _select_map_plan(plan_id: str | None, region: str | None) -> dict[str, Any] | None:
    plans = list_entities("map_plans")
    if plan_id:
        for plan in plans:
            if str(plan.get("id")) == plan_id:
                return plan
        return None
    if region:
        regional = [p for p in plans if str(p.get("region") or "") == region]
        if regional:
            return sorted(regional, key=lambda p: str(p.get("id") or ""), reverse=True)[0]
    if not plans:
        return None
    return sorted(plans, key=lambda p: str(p.get("id") or ""), reverse=True)[0]


def build_layout_preview(
    *,
    plan_id: str | None = None,
    region: str | None = None,
    include_briefs: bool = True,
    include_world_intents: bool = True,
) -> dict[str, Any]:
    """Compose normalized 2D layout geometry for the native preview panel."""
    plan = _select_map_plan(plan_id, region)
    features: list[dict[str, Any]] = []
    plan_meta: dict[str, Any] | None = None
    plan_bounds: dict[str, int] | None = None
    seed = "layout-preview"
    hub: tuple[int, int, int] = (0, 64, 0)
    region_name = str(region or "").strip()

    if plan:
        try:
            validated = validate_map_plan(plan)
            seed = str(validated.get("seed") or seed)
            region_name = region_name or str(validated.get("region") or "")
            origin = validated["origin"]
            hub = (origin["x"], origin["y"], origin["z"])
            plan_bounds = {
                "x1": int(validated["bounds"]["x1"]),
                "z1": int(validated["bounds"]["z1"]),
                "x2": int(validated["bounds"]["x2"]),
                "z2": int(validated["bounds"]["z2"]),
            }
            features.extend(normalize_plot_features(plan))
            plan_meta = {
                "id": validated["id"],
                "title": validated["title"],
                "region": validated["region"],
                "status": str(plan.get("status") or "planned"),
                "source": validated.get("source"),
                "estimated_blocks": validated.get("estimated_blocks"),
            }
        except MapPlanError:
            plan_meta = None

    if include_briefs:
        briefs = list_entities("build_briefs")
        if region_name:
            briefs = [b for b in briefs if str(b.get("region") or "") == region_name]
        pending = [
            b
            for b in briefs
            if str(b.get("status") or "") in {"pending_builder", "planned", "partial", "applied"}
        ]
        features.extend(normalize_build_brief_features(pending[:12], seed=seed, hub=hub))

    if include_world_intents:
        npcs = _list_npcs_for_region(region_name or None)
        pending_npcs = [
            n
            for n in npcs
            if str(n.get("world_status") or "pending_world") in {"pending_world", "partial"}
            or str(n.get("source") or "") == "narrative_workspace"
        ]
        features.extend(normalize_world_intent_features(pending_npcs[:12], seed=seed, hub=hub))

    bounds = _compute_bounds(features, plan_bounds)
    width = bounds["x2"] - bounds["x1"]
    depth = bounds["z2"] - bounds["z1"]
    center_x = (bounds["x1"] + bounds["x2"]) // 2
    center_z = (bounds["z1"] + bounds["z2"]) // 2

    counts = {
        "plots": sum(1 for f in features if f.get("source") == "map_plan"),
        "build_briefs": sum(1 for f in features if f.get("kind") == "build_brief"),
        "npc_intents": sum(1 for f in features if f.get("kind") == "npc_intent"),
        "landmarks": sum(1 for f in features if f.get("kind") == "landmark"),
        "total": len(features),
    }

    empty = counts["total"] == 0
    return {
        "ok": True,
        "empty": empty,
        "mode": "planned",
        "note": "本預覽為 Linkin 計畫／意圖的 2D 示意，不代表遊戲內已落地。",
        "has_map_plan": plan_meta is not None,
        "map_plan": plan_meta,
        "region": region_name or (plan_meta or {}).get("region"),
        "bounds": bounds,
        "view": {
            "width": width,
            "depth": depth,
            "center": {"x": center_x, "z": center_z},
        },
        "legend": LEGEND_ITEMS,
        "features": features,
        "counts": counts,
        "layout_summary": {
            "feature_count": counts["total"],
            "bounds": bounds,
            "has_map_plan": plan_meta is not None,
            "region": region_name or (plan_meta or {}).get("region"),
        },
        "generated_at": time.time(),
    }


__all__ = [
    "build_layout_preview",
    "normalize_build_brief_features",
    "normalize_plot_features",
    "normalize_world_intent_features",
]
