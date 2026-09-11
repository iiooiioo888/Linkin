"""積分池類型與常數（v6.0 — 不可轉贈／不可提現）。"""

from __future__ import annotations

POOL_MONTHLY_GRANT = "monthly_grant"
POOL_PURCHASED = "purchased"
POOL_CONTRIBUTION_UNLOCKED = "contribution_unlocked"
POOL_CONTRIBUTION_LOCKED = "contribution_locked"
POOL_LOCKED = "locked"

# 向後相容別名
POOL_CONTRIBUTION = POOL_CONTRIBUTION_UNLOCKED

ALL_POOL_TYPES = (
    POOL_MONTHLY_GRANT,
    POOL_PURCHASED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_CONTRIBUTION_LOCKED,
    POOL_LOCKED,
)

# 扣款順序：僅 monthly_grant → purchased（貢獻池須先轉換）
SPEND_ORDER = (POOL_MONTHLY_GRANT, POOL_PURCHASED)

# 貢獻積分：未鎖定轉換比率 1:0.4
CONTRIBUTION_UNLOCKED_CONVERT_RATIO = 0.4
CONTRIBUTION_UNLOCKED_HALF_LIFE_MONTHS = 3
CONTRIBUTION_UNLOCKED_DECAY = 0.8

# 貢獻積分：鎖定期與倍率（Phase 1 基礎）
CONTRIBUTION_LOCK_TIERS: dict[int, float] = {30: 1.02, 90: 1.08, 180: 1.20}

# 廠商路由權重
VENDOR_TIER_WEIGHTS = {"标准": 1.0, "优选": 1.2, "战略": 1.5, "standard": 1.0, "preferred": 1.2, "strategic": 1.5}
