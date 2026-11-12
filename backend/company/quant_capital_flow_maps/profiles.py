"""策略分類資金流參數與 profile 合併（確定性）。"""

from __future__ import annotations

from typing import Any

# 依策略分類的預設資金流參數（可被 query 覆寫）
_CATEGORY_PROFILES: dict[str, dict[str, Any]] = {
    "ma": {
        "cash_buffer_pct": 20,
        "margin_pct": 70,
        "reserve_pct": 10,
        "position_pct": 80,
        "stop_loss_pct": 6.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": True,
        "long_pct": 70,
        "short_pct": 0,
    },
    "momentum": {
        "cash_buffer_pct": 25,
        "margin_pct": 60,
        "reserve_pct": 15,
        "position_pct": 75,
        "stop_loss_pct": 5.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 60,
        "short_pct": 0,
    },
    "mean_reversion": {
        "cash_buffer_pct": 30,
        "margin_pct": 55,
        "reserve_pct": 15,
        "position_pct": 70,
        "stop_loss_pct": 4.0,
        "daily_loss_limit_pct": 1.5,
        "short_enabled": False,
        "intraday": False,
        "rebalance": True,
        "long_pct": 55,
        "short_pct": 0,
    },
    "volatility": {
        "cash_buffer_pct": 25,
        "margin_pct": 60,
        "reserve_pct": 15,
        "position_pct": 75,
        "stop_loss_pct": 0.0,
        "trailing_stop_pct": 8.0,
        "daily_loss_limit_pct": 2.5,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 60,
        "short_pct": 0,
    },
    "trend": {
        "cash_buffer_pct": 20,
        "margin_pct": 65,
        "reserve_pct": 15,
        "position_pct": 80,
        "stop_loss_pct": 8.0,
        "daily_loss_limit_pct": 3.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 65,
        "short_pct": 0,
    },
    "breakout": {
        "cash_buffer_pct": 25,
        "margin_pct": 60,
        "reserve_pct": 15,
        "position_pct": 75,
        "stop_loss_pct": 6.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": True,
        "rebalance": False,
        "long_pct": 60,
        "short_pct": 0,
    },
    "composite": {
        "cash_buffer_pct": 25,
        "margin_pct": 55,
        "reserve_pct": 20,
        "position_pct": 75,
        "stop_loss_pct": 6.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": True,
        "intraday": False,
        "rebalance": True,
        "long_pct": 40,
        "short_pct": 20,
    },
    "pattern": {
        "cash_buffer_pct": 30,
        "margin_pct": 55,
        "reserve_pct": 15,
        "position_pct": 70,
        "stop_loss_pct": 5.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 55,
        "short_pct": 0,
    },
    "ml": {
        "cash_buffer_pct": 40,
        "margin_pct": 40,
        "reserve_pct": 20,
        "position_pct": 60,
        "stop_loss_pct": 5.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 40,
        "short_pct": 0,
    },
}

_DEFAULT_PROFILE: dict[str, Any] = {
    "cash_buffer_pct": 25,
    "margin_pct": 60,
    "reserve_pct": 15,
    "position_pct": 75,
    "stop_loss_pct": 6.0,
    "trailing_stop_pct": 0.0,
    "daily_loss_limit_pct": 2.0,
    "short_enabled": False,
    "intraday": False,
    "rebalance": False,
    "long_pct": 40,
    "short_pct": 20,
}

def _merge_profile(category: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(_DEFAULT_PROFILE)
    base.update(_CATEGORY_PROFILES.get(category, {}))
    if overrides:
        for key, val in overrides.items():
            if val is not None and val != "":
                base[key] = val
    # 保證比例加總合理
    total_alloc = base["cash_buffer_pct"] + base["margin_pct"] + base["reserve_pct"]
    if total_alloc != 100:
        scale = 100.0 / total_alloc if total_alloc else 1.0
        base["cash_buffer_pct"] = round(base["cash_buffer_pct"] * scale)
        base["margin_pct"] = round(base["margin_pct"] * scale)
        base["reserve_pct"] = 100 - base["cash_buffer_pct"] - base["margin_pct"]
    if not base.get("short_enabled"):
        base["short_pct"] = 0
        base["long_pct"] = base.get("margin_pct", 60)
    return base
