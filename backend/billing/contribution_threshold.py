"""動態鎖倉閾值演算法（v6.0 — 非固定 50）。"""
from __future__ import annotations

LOCK_THRESHOLD_BASE = 30.0
LOCK_THRESHOLD_CAP = 200.0

_PLAN_FLOOR: dict[str, float] = {
    "free": 50.0,
    "starter": 45.0,
    "pro": 40.0,
    "business": 35.0,
    "enterprise": 30.0,
}


def compute_lock_threshold(
    *,
    unlocked: float,
    locked: float,
    plan_id: str = "free",
    lifetime_contribution: float | None = None,
) -> float:
    """依方案底線、累積貢獻與當前池餘額計算可轉鎖倉閾值。"""
    floor = _PLAN_FLOOR.get(plan_id, 50.0)
    accumulated = lifetime_contribution if lifetime_contribution is not None else (unlocked + locked)
    growth = min(LOCK_THRESHOLD_CAP - floor, accumulated * 0.12)
    dynamic = LOCK_THRESHOLD_BASE + growth
    # 高鎖倉比例時略降閾值，鼓勵長期鎖倉
    if accumulated > 0 and locked / accumulated >= 0.6:
        dynamic *= 0.9
    return round(max(floor, min(LOCK_THRESHOLD_CAP, dynamic)), 2)
