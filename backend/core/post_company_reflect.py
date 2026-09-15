"""公司任務完成後反思閉環模式（SSE、Task API、LangGraph 共用）。"""

from __future__ import annotations

import os


def post_company_reflect_mode() -> str:
    """公司任務完成後反思閉環：off（預設）| evaluate | full。"""
    legacy_skip = os.getenv("EVOL_SKIP_POST_COMPANY_REFLECT", "").strip().lower()
    if legacy_skip in ("1", "true", "yes", "on"):
        return "off"
    raw = os.getenv("EVOL_POST_COMPANY_REFLECT", "off").strip().lower()
    if raw in ("0", "off", "skip", "false", "no", ""):
        return "off"
    if raw in ("evaluate", "eval", "once"):
        return "evaluate"
    return "full"
