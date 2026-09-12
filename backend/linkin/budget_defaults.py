"""靈境子角色預算預設：依崗位（總監／執行者／審查員／記錄員）分級。

0 = 不限（role_catalog 慣例）；Linkin 種子角色使用正值預設，讓監控中心可顯示
已用／上限／剩餘。AI 預算（LLM API）與雲服務預算（Docker＋阿里雲）分開核算。
"""

from __future__ import annotations

from typing import Any

from backend.company.role_catalog import BUDGET_USD_FIELDS
from backend.linkin.prompts import ROLE_EXECUTOR, ROLE_REVIEWER, ROLE_SCRIBE

# 總監（L1）：部門分解與委派，AI／雲用量最高
DIRECTOR_BUDGETS: dict[str, float] = {
    "daily_budget_usd": 25.0,
    "weekly_budget_usd": 100.0,
    "monthly_budget_usd": 350.0,
    "cloud_daily_budget_usd": 15.0,
    "cloud_weekly_budget_usd": 60.0,
    "cloud_monthly_budget_usd": 200.0,
}

# 執行者（L2）：主力生成與工具呼叫
EXECUTOR_BUDGETS: dict[str, float] = {
    "daily_budget_usd": 12.0,
    "weekly_budget_usd": 50.0,
    "monthly_budget_usd": 180.0,
    "cloud_daily_budget_usd": 8.0,
    "cloud_weekly_budget_usd": 30.0,
    "cloud_monthly_budget_usd": 100.0,
}

# 審查員（L3）：評分與退回，以讀取為主
REVIEWER_BUDGETS: dict[str, float] = {
    "daily_budget_usd": 5.0,
    "weekly_budget_usd": 20.0,
    "monthly_budget_usd": 70.0,
    "cloud_daily_budget_usd": 2.0,
    "cloud_weekly_budget_usd": 8.0,
    "cloud_monthly_budget_usd": 25.0,
}

# 記錄員（L4）：RAG 寫入，用量最低
SCRIBE_BUDGETS: dict[str, float] = {
    "daily_budget_usd": 3.0,
    "weekly_budget_usd": 12.0,
    "monthly_budget_usd": 40.0,
    "cloud_daily_budget_usd": 1.0,
    "cloud_weekly_budget_usd": 4.0,
    "cloud_monthly_budget_usd": 12.0,
}

STAFF_BUDGETS: dict[str, dict[str, float]] = {
    ROLE_EXECUTOR: EXECUTOR_BUDGETS,
    ROLE_REVIEWER: REVIEWER_BUDGETS,
    ROLE_SCRIBE: SCRIBE_BUDGETS,
}

BUDGET_TABLE_BY_LEVEL: dict[str, dict[str, float]] = {
    "director": DIRECTOR_BUDGETS,
    "executor": EXECUTOR_BUDGETS,
    "reviewer": REVIEWER_BUDGETS,
    "scribe": SCRIBE_BUDGETS,
}


def infer_staff_key(role_id: str) -> str | None:
    """從角色 id 推斷崗位；總監回傳 None。"""
    rid = (role_id or "").replace("custom_", "")
    if rid.endswith("_director"):
        return None
    for staff in (ROLE_EXECUTOR, ROLE_REVIEWER, ROLE_SCRIBE):
        if rid.endswith(f"_{staff}"):
            return staff
    return None


def budgets_for_role(role_id: str) -> dict[str, float]:
    staff = infer_staff_key(role_id)
    if staff is None:
        return dict(DIRECTOR_BUDGETS)
    return dict(STAFF_BUDGETS.get(staff, EXECUTOR_BUDGETS))


def role_budgets_uncustomized(record: dict[str, Any], overlay: dict[str, Any] | None) -> bool:
    """尚未自訂預算：custom 全為 0 且 settings 覆蓋層無任何預算鍵。"""
    for field in BUDGET_USD_FIELDS:
        if float(record.get(field) or 0) > 0:
            return False
    if overlay:
        for field in BUDGET_USD_FIELDS:
            if field in overlay:
                return False
    return True


def is_linkin_role(record: dict[str, Any]) -> bool:
    tags = record.get("tags") or []
    role_id = str(record.get("id") or "")
    return "linkin" in tags or "linkin_" in role_id
