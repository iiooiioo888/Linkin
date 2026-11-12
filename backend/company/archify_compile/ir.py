"""IR schema 與架構／流程編譯（自 backend.company.archify_compile 抽出）。

_ROLE_TYPE／_ROLE_LAYER／_meta／_nodes／_edges／compile_ir 與 architecture／workflow 編譯。
"""

from __future__ import annotations

import math
from typing import Any

from .labels import _compact, _short_label, _sid
from .layout import _grid_spine

_ROLE_TYPE = {
    "frontend": "frontend",
    "api": "backend",
    "service": "backend",
    "data": "database",
    "external": "external",
    "backend": "backend",
    "database": "database",
    "cloud": "cloud",
    "security": "security",
    "messagebus": "messagebus",
}


_ROLE_LAYER = ("external", "data", "service", "api", "frontend")


def _meta(ir: dict[str, Any], *, diagram_type: str) -> dict[str, Any]:
    meta = ir.get("meta")
    src = meta if isinstance(meta, dict) else {}
    title = str(src.get("title") or "Archify")
    locale = src.get("locale")
    if locale not in {"en", "zh-CN"}:
        locale = "zh-CN"
    preset = src.get("visual_preset")
    if preset not in {"classic", "signal-flow", "blueprint", "editorial"}:
        preset = "signal-flow"
    return {
        "title": title,
        "locale": locale,
        "animation": "trace",
        "visual_preset": preset,
        "quality_profile": "standard",
    }


def _nodes(ir: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in (ir.get("nodes") or []) if isinstance(n, dict) and n.get("id")]


def _edges(ir: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in (ir.get("edges") or []) if isinstance(e, dict) and e.get("from") and e.get("to")]


def _is_official(ir: dict[str, Any]) -> bool:
    return isinstance(ir, dict) and "schema_version" in ir and "diagram_type" in ir


def _kind(ir: dict[str, Any]) -> str:
    raw = str((ir.get("meta") or {}).get("type") or ir.get("diagram_type") or "architecture").lower()
    if raw in {"data-flow", "data_flow", "dataflow"}:
        return "dataflow"
    if raw in {"life-cycle", "life_cycle", "lifecycle"}:
        return "lifecycle"
    if raw == "workflow":
        return "workflow"
    if raw == "sequence":
        return "sequence"
    return "architecture"


def _compile_architecture(ir: dict[str, Any]) -> dict[str, Any]:
    nodes = _nodes(ir)
    if not nodes:
        raise ValueError("architecture 至少需要一個節點")
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in _ROLE_LAYER}
    for node in nodes:
        role = str(node.get("role") or "service")
        buckets[role if role in buckets else "service"].append(node)
    used = [k for k in _ROLE_LAYER if buckets[k]]
    widest = max((len(buckets[k]) for k in used), default=1)
    cols = min(6, max(3, widest))
    cell_w, cell_h, gap_x, gap_y = 132, 58, 40, 64
    origin = (40, 72)
    components: list[dict[str, Any]] = []
    row = 0
    for role in used:
        items = buckets[role]
        for i, node in enumerate(items):
            components.append(
                _compact(
                    {
                        "id": _sid(node["id"]),
                        "type": _ROLE_TYPE.get(role, "backend"),
                        "label": _short_label(node.get("label") or node["id"], 10),
                        "sublabel": _short_label(node.get("detail") or node.get("status") or "", 14) or None,
                        "tag": str(node.get("status") or "")[:14] or None,
                        "row": row + i // cols,
                        "col": i % cols,
                        "size": [cell_w, cell_h],
                    }
                )
            )
        row += max(1, math.ceil(len(items) / cols))
    connections = _grid_spine(components)
    meta = _meta(ir, diagram_type="architecture")
    width = origin[0] + cols * (cell_w + gap_x) - gap_x + 72
    height = origin[1] + max(row, 1) * (cell_h + gap_y) - gap_y + 88
    meta["viewBox"] = [max(320, width), max(240, height)]
    return {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": meta,
        "layout": {
            "mode": "grid",
            "origin": [origin[0], origin[1]],
            "cols": cols,
            "gapX": gap_x,
            "gapY": gap_y,
            "cellW": cell_w,
            "cellH": cell_h,
        },
        "components": components,
        "connections": connections,
    }


def _compile_workflow(ir: dict[str, Any]) -> dict[str, Any]:
    nodes = _nodes(ir)
    if not nodes:
        raise ValueError("workflow 至少需要一個節點")
    authored = [ln for ln in (ir.get("lanes") or []) if isinstance(ln, dict) and ln.get("id")]
    lane_ids: list[str] = []
    lanes: list[dict[str, Any]] = []
    for lane in authored:
        lid = _sid(lane["id"])
        if lid in lane_ids:
            continue
        lane_ids.append(lid)
        lanes.append({"id": lid, "label": str(lane.get("label") or lid)})
    for node in nodes:
        lid = _sid(node.get("lane") or node.get("role") or "signal")
        if lid not in lane_ids:
            lane_ids.append(lid)
            lanes.append({"id": lid, "label": lid})
    if not lanes:
        lanes = [{"id": "main", "label": "流程"}]
        lane_ids = ["main"]
    by_lane: dict[str, list[dict[str, Any]]] = {lid: [] for lid in lane_ids}
    for node in nodes:
        lid = _sid(node.get("lane") or (lane_ids[0] if lane_ids else "main"))
        if lid not in by_lane:
            lid = lane_ids[0]
        by_lane[lid].append(node)
    out_nodes: list[dict[str, Any]] = []
    overflow_i = 0
    for lid in lane_ids:
        for i, node in enumerate(by_lane.get(lid, [])):
            col = i
            use_lane = lid
            if col > 5:
                overflow_i += 1
                use_lane = _sid(f"{lid}_x{overflow_i}")
                if use_lane not in lane_ids:
                    lanes.append({"id": use_lane, "label": f"{lid}+"})
                    lane_ids.append(use_lane)
                col = 0
            role = str(node.get("role") or "service")
            out_nodes.append(
                _compact(
                    {
                        "id": _sid(node["id"]),
                        "lane": use_lane,
                        "col": min(col, 5),
                        "type": _ROLE_TYPE.get(role, "backend"),
                        "label": _short_label(node.get("label") or node["id"], 14),
                        "sublabel": _short_label(node.get("detail") or node.get("status") or "", 16) or None,
                        "tag": str(node.get("status") or "")[:24] or None,
                        "width": 132,
                    }
                )
            )
    edges = []
    seen: set[tuple[str, str]] = set()
    for i, edge in enumerate(_edges(ir)):
        src, dst = _sid(edge["from"]), _sid(edge["to"])
        if src == dst or (src, dst) in seen:
            continue
        seen.add((src, dst))
        edges.append(
            _compact(
                {
                    "id": _sid(f"we{i}_{src}_{dst}"),
                    "from": src,
                    "to": dst,
                    "label": _short_label(edge.get("label") or "", 12) or None,
                    "variant": "emphasis" if i == 0 else "default",
                }
            )
        )
    doc: dict[str, Any] = {
        "schema_version": 2,
        "diagram_type": "workflow",
        "meta": _meta(ir, diagram_type="workflow"),
        "lanes": lanes,
        "nodes": out_nodes,
        "edges": edges,
    }
    return doc
