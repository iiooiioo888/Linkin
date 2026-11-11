"""公司預算的進程級快照（供 API 讀取，由 orchestrator 更新）。

原本這份狀態與更新函式都住在 ``backend/main.py``，導致
``backend/company/orchestrator.py`` 必須反向 import ``backend.main``。
搬到本模組後依賴方向改為單向：``orchestrator → budget_state``、
``main → budget_state``。

注意：更新是**整份替換**而非就地修改，所以讀取方一律走
:func:`get_company_budget_state`，不要在 import 時綁定字典物件——
那會拿到舊快照。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_INITIAL: dict[str, Any] = {
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

_company_budget_state: dict[str, Any] = dict(_INITIAL)


def get_company_budget_state() -> dict[str, Any]:
    """回傳當前公司預算快照（每次呼叫都取最新值）。"""
    return _company_budget_state


def update_company_budget_state(state: dict[str, Any]) -> None:
    """由公司 orchestrator 調用，更新全局預算狀態。"""
    global _company_budget_state
    _company_budget_state = {
        **state,
        "last_updated": datetime.now(UTC).isoformat(),
    }


def reset_company_budget_state() -> None:
    """測試隔離：回到初始空狀態。"""
    global _company_budget_state
    _company_budget_state = dict(_INITIAL)


__all__ = [
    "get_company_budget_state",
    "reset_company_budget_state",
    "update_company_budget_state",
]
