"""RAHO 開關與門檻：環境變數控制的啟用旗標、鎖定門檻與決策 TTL。"""

from __future__ import annotations

import os

from .layers import LOCK_THRESHOLD


def raho_enabled() -> bool:
    return os.getenv("EVOL_RAHO_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def user_grill_enabled() -> bool:
    return raho_enabled() and os.getenv("EVOL_RAHO_USER_GRILL", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def l0_enabled() -> bool:
    return raho_enabled() and os.getenv("EVOL_RAHO_L0", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def mgp_enabled() -> bool:
    return raho_enabled() and os.getenv("EVOL_RAHO_MGP", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def lock_threshold() -> float:
    try:
        return float(os.getenv("EVOL_RAHO_LOCK_THRESHOLD", str(LOCK_THRESHOLD)))
    except ValueError:
        return LOCK_THRESHOLD


def decision_ttl_seconds() -> float:
    """決策逾時（熱馬桶圈）。0 = 立即自動裁決，不阻塞。"""
    try:
        return max(0.0, float(os.getenv("EVOL_RAHO_DECISION_TTL", "60")))
    except ValueError:
        return 60.0
