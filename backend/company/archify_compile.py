"""把簡化 IR 編成 tt-a1i/archify 正式 JSON，並呼叫其 CLI 產出 HTML。

依賴：`frontend` 的 `archify`（file:../vendor/archify），找不到 npm 連結時回退 vendor/archify。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from backend.company.quant_strategy_maps import (
    ARCHIFY_SOURCE,
    archify_strategies,
    strategy_catalog_maps,
    strategy_maps,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".archify_cache"
_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
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


def archify_root() -> Path:
    candidates = (
        ROOT / "frontend" / "node_modules" / "archify",
        ROOT / "vendor" / "archify",
    )
    for path in candidates:
        if (path / "bin" / "archify.mjs").is_file():
            return path
    raise FileNotFoundError("找不到 archify CLI。請在 frontend 執行 npm install（archify 已列為 file:../vendor/archify）。")


def archify_bin() -> Path:
    return archify_root() / "bin" / "archify.mjs"


def _sid(raw: Any, fallback: str = "n") -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw or fallback).strip())
    text = text.strip("_") or fallback
    if not text[0].isalpha():
        text = f"n_{text}"
    if not _ID_RE.match(text):
        text = "n_" + re.sub(r"[^a-zA-Z0-9_]", "", text)
    return text[:72]


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _short_label(raw: Any, limit: int = 16) -> str:
    text = str(raw or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _named_connections(edges: list[dict[str, Any]], *, labeled: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, edge in enumerate(edges):
        src, dst = _sid(edge["from"]), _sid(edge["to"])
        if src == dst or (src, dst) in seen:
            continue
        seen.add((src, dst))
        label = _short_label(edge.get("label") or "", 12) if labeled else ""
        out.append(
            _compact(
                {
                    "id": _sid(f"e{i}_{src}_{dst}"),
                    "from": src,
                    "to": dst,
                    "label": label or None,
                    "variant": "emphasis" if i == 0 else "default",
                }
            )
        )
    return out


def _grid_spine(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只連同行相鄰與每列第一顆，避免穿越節點。"""
    by_row: dict[int, list[dict[str, Any]]] = {}
    for node in components:
        by_row.setdefault(int(node["row"]), []).append(node)
    connections: list[dict[str, Any]] = []
    n = 0
    for row in sorted(by_row):
        items = sorted(by_row[row], key=lambda c: int(c["col"]))
        for left, right in itertools.pairwise(items):
            connections.append(
                {
                    "id": _sid(f"h{n}_{left['id']}_{right['id']}"),
                    "from": left["id"],
                    "to": right["id"],
                    "route": "orthogonal-h",
                }
            )
            n += 1
    rows = sorted(by_row)
    for upper, lower in itertools.pairwise(rows):
        a = min(by_row[upper], key=lambda c: int(c["col"]))
        b = min(by_row[lower], key=lambda c: int(c["col"]))
        if a["id"] == b["id"]:
            continue
        connections.append(
            {
                "id": _sid(f"v{n}_{a['id']}_{b['id']}"),
                "from": a["id"],
                "to": b["id"],
                "route": "orthogonal-v",
            }
        )
        n += 1
    return connections


def _meta(ir: dict[str, Any], *, diagram_type: str) -> dict[str, Any]:
    src = ir.get("meta") if isinstance(ir.get("meta"), dict) else {}
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


def compile_ir(ir: dict[str, Any]) -> dict[str, Any]:
    """簡化 IR → Archify 正式 schema。已是正式文件則原樣回傳（補 meta）。"""
    if not isinstance(ir, dict):
        raise ValueError("IR 必須是物件")
    if _is_official(ir):
        return ir
    kind = _kind(ir)
    if kind == "workflow":
        return _compile_workflow(ir)
    if kind == "dataflow":
        return _compile_dataflow(ir)
    if kind == "lifecycle":
        return _compile_lifecycle(ir)
    return _compile_architecture(ir)


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


def _node_executable() -> str:
    found = shutil.which("node")
    if not found:
        raise FileNotFoundError("需要 Node.js >= 18 才能呼叫 archify CLI")
    return found


def _prepare_html(html: str) -> str:
    """iframe 內強制 SVG 有高度，避免官方 `svg{width:100%}` 在沙箱裡塌成空白。"""
    extra = (
        '<style id="linkin-archify-iframe">'
        "html,body{min-height:100%;height:auto;}"
        ".diagram-container{max-width:100%;overflow:auto!important;}"
        ".diagram-container svg,svg[viewBox]{display:block;width:100%!important;"
        "max-width:100%;height:auto!important;min-height:240px;}"
        "</style>"
    )
    if 'id="linkin-archify-iframe"' not in html:
        html = html.replace("</head>", extra + "</head>", 1)
    return html


def render_document(document: dict[str, Any], *, timeout: int = 45) -> str:
    """呼叫 `archify render` 產出獨立 HTML。"""
    diagram_type = str(document.get("diagram_type") or "architecture")
    if diagram_type == "data-flow":
        diagram_type = "dataflow"
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    html_path = CACHE_DIR / f"{diagram_type}-{digest}.html"
    if html_path.is_file() and html_path.stat().st_size > 1000:
        return _prepare_html(html_path.read_text(encoding="utf-8"))
    node = _node_executable()
    bin_path = archify_bin()
    with tempfile.TemporaryDirectory(prefix="archify-") as tmp:
        src = Path(tmp) / f"{diagram_type}.json"
        dst = Path(tmp) / f"{diagram_type}.html"
        src.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        env = os.environ.copy()
        env["ARCHIFY_QUALITY_PROFILE"] = "standard"
        env["ARCHIFY_UPDATE_CHECK_DISABLED"] = "1"
        proc = subprocess.run(
            [node, str(bin_path), "render", diagram_type, str(src), str(dst), "--quality", "standard"],
            cwd=str(archify_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
        if proc.returncode != 0 or not dst.is_file():
            err = (proc.stderr or proc.stdout or "archify render 失敗").strip()
            raise RuntimeError(err[-2000:])
        html = dst.read_text(encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return _prepare_html(html)


def render_ir(ir: dict[str, Any]) -> dict[str, Any]:
    document = compile_ir(ir)
    html = render_document(document)
    return {
        "ok": True,
        "html": html,
        "diagram_type": document.get("diagram_type"),
        "title": (document.get("meta") or {}).get("title"),
        "engine": "archify",
        "source": ARCHIFY_SOURCE,
        "document": document,
    }


def resolve_strategy_ir(view: str = "overview", id: str = "", kind: str = "") -> dict[str, Any]:
    """依實驗室 view 取出要渲染的簡化 IR。"""
    want = (view or "overview").strip().lower()
    key = (id or "").strip()
    flavor = (kind or "").strip().lower()
    if want in {"evoloop", "system"}:
        from backend.services.lab_tools import get_evoloop_architecture

        return get_evoloop_architecture()
    if want in {"overview", "catalog", "all", ""}:
        return strategy_catalog_maps()["overview"]
    if want in {"data_flow", "data-flow", "flow"}:
        return strategy_catalog_maps()["data_flow"]
    if want == "lifecycle" and not key:
        return strategy_catalog_maps()["lifecycle"]
    payload = archify_strategies(view=want, id=key)
    if not payload.get("ok"):
        raise ValueError(payload.get("error") or "無法取得策略圖")
    if "ir" in payload:
        return payload["ir"]
    if want in {"strategy", "workflow"} or key:
        detail = payload if payload.get("workflow") else strategy_maps(key)
        if flavor == "lifecycle":
            return detail["lifecycle"]
        if flavor == "architecture":
            return detail["architecture"]
        return detail["workflow"]
    if "overview" in payload:
        return payload["overview"]
    raise ValueError("沒有可渲染的 IR")


def render_view(view: str = "overview", id: str = "", kind: str = "") -> dict[str, Any]:
    return render_ir(resolve_strategy_ir(view=view, id=id, kind=kind))
