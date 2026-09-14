"""UI 語系 → LLM system 疊加（聊天／簡單任務管線）。"""

from __future__ import annotations

import os


def ui_language_system_overlay(ui_language: str | None) -> str:
    """依前端 i18n 語系回傳 system 前綴；空字串表示不追加。"""
    raw = (ui_language or os.getenv("EVOL_DEFAULT_UI_LANGUAGE") or "zh-TW").strip()
    code = raw.lower().replace("_", "-")
    if code in {"zh-tw", "zh-hant", "zh-hk", "zh-mo"}:
        return (
            "【介面語言】使用者介面為繁體中文（zh-Hant）。"
            "請一律以繁體中文（Traditional Chinese，台港澳用字）撰寫可見回覆，勿使用簡體中文。"
        )
    if code.startswith("en"):
        return (
            "【UI language】The user interface is English. "
            "Reply in English unless the user explicitly requests another language."
        )
    if code in {"zh", "zh-cn"}:
        return "【介面語言】使用者介面為中文。請以繁體中文回覆，除非使用者明確要求其他語言。"
    return ""


def normalize_ui_language(ui_language: str | None) -> str:
    raw = (ui_language or os.getenv("EVOL_DEFAULT_UI_LANGUAGE") or "zh-TW").strip()
    return raw or "zh-TW"
