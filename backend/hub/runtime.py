"""Hub 執行期單例：store / cache / budget / circuit / db。測試可 reset。"""

from __future__ import annotations

from backend.hub.budget_guard import DailyBudgetLedger
from backend.hub.cache import SemanticCache
from backend.hub.circuit import CircuitRegistry
from backend.hub.db import Database, init_database
from backend.hub.store import HubStore


class HubRuntime:
    def __init__(self, use_database: bool = True) -> None:
        """初始化 Hub 執行期。
        
        Args:
            use_database: 是否啟用 SQLite 持久層。預設為 True。
        """
        self.store = HubStore()
        self.cache = SemanticCache()
        self.budget = DailyBudgetLedger()
        self.circuits = CircuitRegistry()
        self.upstream_calls: list[dict] = []
        self.db: Database | None = None

        # 初始化數據庫（若啟用）
        self._use_database = use_database
        if use_database:
            try:
                self.db = init_database()
            except Exception:
                # 若數據庫初始化失敗，回退到內存存儲
                self._use_database = False
                self.db = None
    
    def reset(self) -> None:
        self.store.reset()
        self.cache.reset()
        self.budget.reset()
        self.circuits.reset()
        self.upstream_calls.clear()
        if self.db:
            # 重置數據庫（開發環境）
            pass  # SQLite 會保留數據以實現持久化


runtime = HubRuntime()


def reset_runtime() -> None:
    runtime.reset()
