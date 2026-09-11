"""積分池類型與常數（不可轉贈／不可提現）。"""

from __future__ import annotations

POOL_MONTHLY_GRANT = "monthly_grant"
POOL_PURCHASED = "purchased"
POOL_CONTRIBUTION = "contribution"
POOL_LOCKED = "locked"

ALL_POOL_TYPES = (POOL_MONTHLY_GRANT, POOL_PURCHASED, POOL_CONTRIBUTION, POOL_LOCKED)

# 扣款順序：月度贈送 → 已購買 FIFO
SPEND_ORDER = (POOL_MONTHLY_GRANT, POOL_PURCHASED)

# Phase 2 stub：貢獻積分鎖定期（天）
CONTRIBUTION_LOCK_DAYS = 30
