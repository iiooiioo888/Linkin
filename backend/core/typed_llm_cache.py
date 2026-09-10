"""分類型 TTL 的 LLM 快取（C-LLM-003／TODO §5.3）。

契約：
- 快取依**類型**設定 TTL（角色 Prompt 片段可長、評估結果需短）。
- **審計／憲兵（L1）路徑預設旁路（TTL=0）**，禁止快取誤傷需新鮮上下文的路徑。
- 每次查詢附路由原因碼（``cache_hit``／``cache_bypass:*``／``cache_miss``）。

與 ``llm_cache.py``（兩級通用快取）分工：本模組是**契約層**，
負責「哪類路徑能不能快取、TTL 多長」的策略裁定；實際存取仍走通用快取。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

# ── 路由原因碼 ──
REASON_CACHE_HIT = "cache_hit"
REASON_CACHE_MISS = "cache_miss"
REASON_BYPASS_AUDIT = "cache_bypass:audit_path"
REASON_BYPASS_INSPECTOR = "cache_bypass:inspector_path"
REASON_TTL_ZERO = "cache_bypass:ttl_zero"


class CacheKind(str, Enum):
    """快取類型（§5.3 分類型 TTL）。"""

    ROLE_PROMPT = "role_prompt"      # 角色 Prompt 片段：長 TTL
    EVALUATION = "evaluation"        # 評估結果：短 TTL
    REFLECTION = "reflection"        # 反思迴圈中間產物：中 TTL
    AUDIT_CONTEXT = "audit_context"  # 審計路徑：預設旁路
    INSPECTOR_CONTEXT = "inspector_context"  # L1 憲兵路徑：預設旁路


# 預設 TTL（秒）；0 = 永不快取（旁路）
DEFAULT_TTL: dict[CacheKind, float] = {
    CacheKind.ROLE_PROMPT: 86400.0,   # 24h：角色 Prompt 片段穩定
    CacheKind.EVALUATION: 300.0,      # 5min：評估結果需相對新鮮
    CacheKind.REFLECTION: 1800.0,     # 30min
    CacheKind.AUDIT_CONTEXT: 0.0,     # 審計預設旁路（C-LLM-003）
    CacheKind.INSPECTOR_CONTEXT: 0.0, # 憲兵預設旁路（C-LLM-003）
}

# 審計／憲兵路徑即使被顯式設定 TTL 也不允許 > 0（除非顯式覆寫 allow_override）
_PROTECTED_KINDS = frozenset({CacheKind.AUDIT_CONTEXT, CacheKind.INSPECTOR_CONTEXT})


@dataclass(frozen=True)
class CacheLookup:
    hit: bool
    value: str | None
    reason_code: str


@dataclass
class _Entry:
    value: str
    created_at: float
    ttl: float

    def expired(self, now: float) -> bool:
        return (now - self.created_at) > self.ttl


@dataclass
class TypedLLMCache:
    """分類型 TTL 快取；審計／憲兵路徑預設 TTL=0。"""

    ttl_map: dict[CacheKind, float] = field(default_factory=lambda: dict(DEFAULT_TTL))
    clock: callable = time.monotonic
    _store: dict[tuple[CacheKind, str], _Entry] = field(default_factory=dict)

    def ttl_for(self, kind: CacheKind) -> float:
        return float(self.ttl_map.get(kind, 0.0))

    def set_ttl(self, kind: CacheKind, ttl: float, *, allow_protected_override: bool = False) -> None:
        """設定 TTL；受保護路徑（審計／憲兵）預設禁止設為 > 0。"""
        if kind in _PROTECTED_KINDS and ttl > 0 and not allow_protected_override:
            raise ValueError(f"{kind.value} 為受保護路徑，禁止設定 TTL > 0（C-LLM-003）")
        self.ttl_map[kind] = float(ttl)

    def get(self, kind: CacheKind, key: str) -> CacheLookup:
        ttl = self.ttl_for(kind)
        if ttl <= 0:
            reason = (
                REASON_BYPASS_AUDIT if kind is CacheKind.AUDIT_CONTEXT
                else REASON_BYPASS_INSPECTOR if kind is CacheKind.INSPECTOR_CONTEXT
                else REASON_TTL_ZERO
            )
            return CacheLookup(hit=False, value=None, reason_code=reason)
        entry = self._store.get((kind, key))
        if entry is None:
            return CacheLookup(hit=False, value=None, reason_code=REASON_CACHE_MISS)
        if entry.expired(self.clock()):
            del self._store[(kind, key)]
            return CacheLookup(hit=False, value=None, reason_code=REASON_CACHE_MISS)
        return CacheLookup(hit=True, value=entry.value, reason_code=REASON_CACHE_HIT)

    def put(self, kind: CacheKind, key: str, value: str) -> bool:
        """寫入快取；TTL=0 路徑直接拒絕寫入（回傳 False）。"""
        ttl = self.ttl_for(kind)
        if ttl <= 0:
            return False
        self._store[(kind, key)] = _Entry(value=value, created_at=self.clock(), ttl=ttl)
        return True

    @property
    def size(self) -> int:
        return len(self._store)
