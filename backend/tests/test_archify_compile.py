"""Archify 正式 schema 編譯與 CLI 渲染。"""

from __future__ import annotations

import shutil

import pytest

from backend.company.archify_compile import compile_ir, render_view, resolve_strategy_ir
from backend.company.quant_strategy_maps import (
    overview_architecture,
    overview_data_flow,
    strategy_maps,
)
from backend.services.lab_tools import get_evoloop_architecture


def test_compile_overview_architecture():
    doc = compile_ir(overview_architecture())
    assert doc["diagram_type"] == "architecture"
    assert doc["layout"]["mode"] == "grid"
    ids = {c["id"] for c in doc["components"]}
    assert "feeds" in ids
    assert "cat_ma" in ids
    assert "dual_ma" in ids
    assert "enhanced_volume" in ids
    assert "single_volume" in ids
    assert doc["connections"]
    assert doc["meta"]["locale"] == "zh-CN"
    for component in doc["components"]:
        assert component["type"] in {
            "frontend",
            "backend",
            "database",
            "cloud",
            "security",
            "messagebus",
            "external",
        }


def test_compile_dual_ma_workflow():
    ir = strategy_maps("dual_ma")["workflow"]
    doc = compile_ir(ir)
    assert doc["diagram_type"] == "workflow"
    assert doc["schema_version"] == 2
    assert doc["lanes"]
    cols = {(n["lane"], n["col"]) for n in doc["nodes"]}
    assert len(cols) == len(doc["nodes"])
    assert all(0 <= n["col"] <= 5 for n in doc["nodes"])


def test_compile_enhanced_volume_and_dataflow_lifecycle():
    enh = compile_ir(strategy_maps("enhanced_volume")["workflow"])
    ids = {n["id"] for n in enh["nodes"]}
    assert {"vol", "rsi", "bb", "kdj", "enh"} <= ids
    flow = compile_ir(overview_data_flow())
    assert flow["diagram_type"] == "dataflow"
    assert 2 <= len(flow["stages"]) <= 5
    assert all(f.get("label") for f in flow["flows"])
    life = compile_ir(strategy_maps("dual_ma")["lifecycle"])
    assert life["diagram_type"] == "lifecycle"
    assert life["states"]
    assert len(life["lanes"]) <= 4


def test_resolve_views():
    overview = resolve_strategy_ir("overview")
    assert overview["meta"]["type"] == "architecture"
    group = resolve_strategy_ir("group", id="ma")
    assert group["meta"]["category"] == "ma"
    wf = resolve_strategy_ir("strategy", id="rsi", kind="workflow")
    assert wf["meta"]["type"] == "workflow"
    evoloop = resolve_strategy_ir("evoloop")
    assert evoloop["nodes"]


def test_prepare_html_keeps_svg_height():
    from backend.company.archify_compile import _prepare_html

    html = _prepare_html("<html><head></head><body><svg viewBox='0 0 10 10'></svg></body></html>")
    assert 'id="linkin-archify-iframe"' in html
    assert "height:auto!important" in html
    assert "min-height:240px" in html


def test_compile_evoloop_ir():
    doc = compile_ir(get_evoloop_architecture())
    assert doc["diagram_type"] == "architecture"
    assert any(c["id"] == "graph" for c in doc["components"])


def test_compile_ir_script_stdout(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    script = root / "backend" / "scripts" / "archify_compile_ir.py"
    src = tmp_path / "ir.json"
    src.write_text(json.dumps(overview_architecture(), ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), str(src)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(root),
        check=False,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["diagram_type"] == "architecture"
    assert doc["components"]


@pytest.mark.skipif(not shutil.which("node"), reason="需要 Node.js 呼叫 archify CLI")
def test_archify_cli_renders_strategy_maps():
    overview = render_view("overview")
    assert overview["ok"] is True
    assert "<svg" in overview["html"].lower()
    workflow = render_view("strategy", id="dual_ma", kind="workflow")
    assert "<svg" in workflow["html"].lower()
    flow = render_view("data_flow")
    assert "<svg" in flow["html"].lower()
