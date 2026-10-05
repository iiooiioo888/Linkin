"""公司任務完成後反思閉環模式（SSE、Task API、LangGraph 共用）。"""

from __future__ import annotations

import os


def _normalize_mode(raw: str) -> str:
    value = raw.strip().lower()
    if value in ("0", "off", "skip", "false", "no", ""):
        return "off"
    if value in ("evaluate", "eval", "once"):
        return "evaluate"
    return "full"


def post_company_reflect_mode() -> str:
    """公司任務完成後反思閉環：off（預設）| evaluate | full。

    優先序：EVOL_SKIP_POST_COMPANY_REFLECT → EVOL_POST_COMPANY_REFLECT →
    cost_speed.json ``post_company_reflect``。
    """
    legacy_skip = os.getenv("EVOL_SKIP_POST_COMPANY_REFLECT", "").strip().lower()
    if legacy_skip in ("1", "true", "yes", "on"):
        return "off"
    env_raw = os.getenv("EVOL_POST_COMPANY_REFLECT")
    if env_raw is not None and env_raw.strip() != "":
        return _normalize_mode(env_raw)
    try:
        from backend.core.cost_speed_router import post_company_reflect_config_value

        return post_company_reflect_config_value()
    except Exception:
        return "off"


def post_company_reflect_resolution() -> dict[str, str]:
    """解析來源（供設定 API 與測試）。"""
    legacy_skip = os.getenv("EVOL_SKIP_POST_COMPANY_REFLECT", "").strip().lower()
    if legacy_skip in ("1", "true", "yes", "on"):
        return {"effective": "off", "source": "env_skip"}
    env_raw = os.getenv("EVOL_POST_COMPANY_REFLECT")
    if env_raw is not None and env_raw.strip() != "":
        return {"effective": _normalize_mode(env_raw), "source": "env"}
    try:
        from backend.core.cost_speed_router import post_company_reflect_config_value

        cfg = post_company_reflect_config_value()
        return {"effective": cfg, "source": "config"}
    except Exception:
        return {"effective": "off", "source": "default"}
