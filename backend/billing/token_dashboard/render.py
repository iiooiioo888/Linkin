"""載入 vendored token-dashboard 模板並渲染 HTML。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SKILL_RENDER = (
    Path(__file__).resolve().parents[3] / ".agents/skills/token-dashboard/scripts/dashboard_render.py"
)


def render_html(data: dict) -> str:
    spec = importlib.util.spec_from_file_location("linkin_token_dashboard_render", _SKILL_RENDER)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"找不到看板模板：{_SKILL_RENDER}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_html(data)
