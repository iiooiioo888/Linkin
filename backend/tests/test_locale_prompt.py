"""UI 語系 → LLM system 疊加。"""

from __future__ import annotations

from backend.core import nodes
from backend.core.locale_prompt import ui_language_system_overlay


def test_ui_language_overlay_zh_tw():
    line = ui_language_system_overlay("zh-TW")
    assert "繁體" in line
    assert "Traditional" in line


def test_ui_language_overlay_en():
    line = ui_language_system_overlay("en")
    assert "English" in line


def test_build_generate_prompt_injects_locale():
    _, system = nodes.build_generate_prompt({"query": "hi", "ui_language": "zh-Hant"})
    assert "繁體" in system
