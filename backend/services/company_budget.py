"""全域公司預算狀態（由 orchestrator 更新、API 讀取）。

自 backend.main 抽出：orchestrator 不需反向 import 應用入口，避免 main ↔ orchestrator
循環依賴；main 只做向後相容的 re-export。
"""

from datetime import datetime, timezone
from typing import Any

_company_budget_state: dict[str, Any] = {
    "api_cost": 0.0,
    "docker_cost": 0.0,
    "aliyun_cost": 0.0,
    "cloud_cost": 0.0,
    "total_spent": 0.0,
    "budget_pressure": 0.0,
    "optimization_suggestions": [],
    "auto_optimized": {},
    "last_updated": "",
}


def update_company_budget_state(state: dict[str, Any]) -> None:
    """由公司 orchestrator 調用，更新全局預算狀態。"""
    global _company_budget_state
    _company_budget_state = {
        **state,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def get_company_budget_state() -> dict[str, Any]:
    """讀取當前全局預算狀態（供監控 API 使用）。"""
    return _company_budget_state
