"""其他圖型編譯（自 backend.company.archify_compile 抽出）。

dataflow／lifecycle 編譯。
"""

from __future__ import annotations

import itertools
from typing import Any

from .ir import _ROLE_TYPE, _edges, _meta, _nodes
from .labels import _compact, _short_label, _sid


def _compile_dataflow(ir: dict[str, Any]) -> dict[str, Any]:
    nodes = _nodes(ir)
    if len(nodes) < 2:
        raise ValueError("dataflow 至少需要兩個節點")
    authored = [ln for ln in (ir.get("lanes") or []) if isinstance(ln, dict) and ln.get("id")]
    stages: list[dict[str, str]] = []
    lane_stage: dict[str, int] = {}
    for lane in authored[:5]:
        lid = _sid(lane["id"])
        lane_stage[lid] = len(stages)
        stages.append({"label": str(lane.get("label") or lid)})
    if len(stages) < 2:
        stages = [{"label": "來源"}, {"label": "處理"}, {"label": "產出"}]
        lane_stage = {}
        role_stage = {"external": 0, "data": 0, "service": 1, "api": 1, "frontend": 2}
    else:
        role_stage = {}
    row_at: dict[int, int] = {}
    out_nodes = []
    for node in nodes:
        lid = _sid(node.get("lane") or "")
        if lid in lane_stage:
            stage = lane_stage[lid]
        else:
            stage = role_stage.get(str(node.get("role") or "service"), min(1, len(stages) - 1))
        stage = min(max(stage, 0), len(stages) - 1)
        row = row_at.get(stage, 0)
        row_at[stage] = row + 1
        role = str(node.get("role") or "service")
        out_nodes.append(
            _compact(
                {
                    "id": _sid(node["id"]),
                    "type": _ROLE_TYPE.get(role, "backend"),
                    "label": _short_label(node.get("label") or node["id"], 14),
                    "sublabel": _short_label(node.get("detail") or "", 16) or None,
                    "tag": str(node.get("status") or "")[:16] or None,
                    "stage": stage,
                    "row": row,
                }
            )
        )
    flows = []
    seen: set[tuple[str, str]] = set()
    for i, edge in enumerate(_edges(ir)):
        src, dst = _sid(edge["from"]), _sid(edge["to"])
        if src == dst or (src, dst) in seen:
            continue
        seen.add((src, dst))
        flows.append(
            _compact(
                {
                    "id": _sid(f"f{i}_{src}_{dst}"),
                    "from": src,
                    "to": dst,
                    "label": _short_label(edge.get("label") or f"{src[:4]}-{dst[:4]}", 10),
                    "labelDy": 28 + (i % 3) * 16,
                    "variant": "emphasis" if i == 0 else "default",
                }
            )
        )
    meta = _meta(ir, diagram_type="dataflow")
    meta["viewBox"] = [1280, 720]
    return {
        "schema_version": 1,
        "diagram_type": "dataflow",
        "meta": meta,
        "stages": stages,
        "nodes": out_nodes,
        "flows": flows,
    }


def _compile_lifecycle(ir: dict[str, Any]) -> dict[str, Any]:
    nodes = _nodes(ir)
    if len(nodes) < 2:
        raise ValueError("lifecycle 至少需要兩個狀態")
    lanes = [
        {"id": "main", "label": "主路徑"},
        {"id": "terminal", "label": "終態／例外"},
    ]
    counts = {ln["id"]: 0 for ln in lanes}
    states = []
    for i, node in enumerate(nodes):
        nid = _sid(node["id"])
        status = str(node.get("status") or "")
        role = str(node.get("role") or "")
        if (
            status == "catalog"
            or nid in {"fail", "block", "blocked", "skip"}
            or role == "frontend"
            or nid in {"stats", "completed"}
        ):
            lane = "terminal"
            typ = "failure" if nid in {"fail", "block", "blocked", "skip"} or status == "catalog" else "success"
        elif i == 0:
            lane, typ = "main", "start"
        else:
            lane, typ = "main", "active"
        limit = 4 if lane == "main" else 2
        col = counts[lane]
        if col > limit:
            other = "terminal" if lane == "main" else "main"
            other_limit = 4 if other == "main" else 2
            if counts[other] <= other_limit:
                lane, col = other, counts[other]
            else:
                continue
        counts[lane] = col + 1
        states.append(
            _compact(
                {
                    "id": nid,
                    "type": typ,
                    "label": _short_label(node.get("label") or node["id"], 14),
                    "sublabel": _short_label(node.get("detail") or status or "", 16) or None,
                    "tag": status[:18] or None,
                    "lane": lane,
                    "col": col,
                    "step": f"{i + 1:02d}" if lane == "main" else None,
                }
            )
        )
    by_lane: dict[str, list[dict[str, Any]]] = {ln["id"]: [] for ln in lanes}
    for state in states:
        by_lane[state["lane"]].append(state)
    transitions = []
    ordered_main = sorted(by_lane["main"], key=lambda s: int(s["col"]))
    for n, (a, b) in enumerate(itertools.pairwise(ordered_main)):
        transitions.append(
            {
                "id": _sid(f"t{n}_{a['id']}_{b['id']}"),
                "from": a["id"],
                "to": b["id"],
                "route": "straight",
            }
        )
    return {
        "schema_version": 1,
        "diagram_type": "lifecycle",
        "meta": _meta(ir, diagram_type="lifecycle"),
        "lanes": lanes,
        "states": states,
        "transitions": transitions,
    }
