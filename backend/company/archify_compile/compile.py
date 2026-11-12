"""CLI 渲染與公開入口（自 backend.company.archify_compile 抽出）。

archify_root／archify_bin／render_document／render_ir／resolve_strategy_ir／render_view。
"""

from __future__ import annotations

import hashlib
import json
import os
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

from .diagrams import _compile_dataflow, _compile_lifecycle
from .ir import _compile_architecture, _compile_workflow, _is_official, _kind

ROOT = Path(__file__).resolve().parents[3]


CACHE_DIR = ROOT / ".archify_cache"


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
    from backend.company.system_flow_maps import resolve_system_flow_ir

    _system_views = {
        "evoloop",
        "system",
        "system-deploy",
        "langgraph",
        "raho",
        "shared-pool",
        "credit-pools",
        "opc",
    }
    if want in _system_views:
        return resolve_system_flow_ir(want)
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
