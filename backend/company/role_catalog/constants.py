"""角色目錄的預設路徑、標籤、值域與預算欄位常數（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from backend.company.state import BudgetTier, RoleCategory, RoleType

logger = logging.getLogger("backend.company.role_catalog")

# 套件化後多一層目錄：parents 再多一層仍指向 backend/，維持原 backend/data/role_catalog*。
DEFAULT_CATALOG_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "role_catalog"
)
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "role_catalog.json"
)

ROLE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
RESERVED_IDS = {rt.value for rt in RoleType}

LEVEL_LABELS: dict[int, str] = {
    0: "最高決策層",
    1: "技術領導層",
    2: "領域領導層",
    3: "執行層",
    4: "支援角色",
}

CATEGORY_LABELS: dict[str, str] = {
    "ui": "UI 設計",
    "css": "樣式",
    "js": "前端邏輯",
    "backend": "後端",
    "test": "測試",
    "devops": "維運",
    "management": "管理",
    "review": "審查",
    "security": "資安",
    "data": "資料",
    "product": "產品",
    "docs": "文件",
    "mobile": "行動端",
    "research": "研究",
    "ai": "AI / Prompt",
    "legal": "合規",
    "finance": "金融／量化",
    "industrial": "工業／OPC",
    "creative": "創意／敘事",
    "crawler": "爬蟲／採集",
    "platform": "平台／GitHub",
    "hub": "AI Hub",
    "memory": "記憶／知識庫",
    "growth": "成長／客戶成功",
}

TIER_VALUES = {t.value for t in BudgetTier}
CATEGORY_VALUES = {c.value for c in RoleCategory}
ROUTING_STRATEGIES = {"cost_first", "speed_first", "quality_first", "manual"}

# AI 使用預算（LLM API）與雲服務預算（Docker + 阿里雲）分開，0=不限
AI_BUDGET_FIELDS = ("daily_budget_usd", "weekly_budget_usd", "monthly_budget_usd")
CLOUD_BUDGET_FIELDS = (
    "cloud_daily_budget_usd",
    "cloud_weekly_budget_usd",
    "cloud_monthly_budget_usd",
)
BUDGET_USD_FIELDS = AI_BUDGET_FIELDS + CLOUD_BUDGET_FIELDS

DEFAULT_RUNTIME: dict[str, Any] = {
    "preferred_model": "",
    "preferred_provider": "",
    "daily_budget_usd": 0.0,
    "weekly_budget_usd": 0.0,
    "monthly_budget_usd": 0.0,
    "cloud_daily_budget_usd": 0.0,
    "cloud_weekly_budget_usd": 0.0,
    "cloud_monthly_budget_usd": 0.0,
    "tools_allowed": [],
    "notes": "",
    "enabled": True,
    "alert_on_error": True,
    "alert_on_budget": True,
    "alert_on_sla": True,
    "temperature": 0.7,
    "max_output_tokens": 4096,
    "timeout_ms": 120000,
    "routing_strategy": "quality_first",
    "failover_models": [],
    "sla_latency_ms": 0,
    "max_retries": 3,
    "language": "zh-TW",
    "always_require_review": False,
    "priority": 3,
    "description": "",
    "max_daily_items": 0,
    "require_human_approval": False,
    "stream_enabled": True,
    "cache_enabled": True,
    "pii_redact": True,
    "mainland_only": False,
    "heartbeat_sec": 0,
    "on_call": False,
    "tags": [],
    "notify_channel": "",
    "quiet_hours": "",
    "context_window": 0,
    "allow_tool_use": True,
    "auto_escalate": True,
}

DEFAULT_MONITOR_PREFS: dict[str, Any] = {
    "poll_interval_ms": 5000,
    "show_disabled": True,
    "show_idle": True,
    "show_custom_only": False,
    "group_by": "level",
    "compact_cards": False,
    "default_desk_tab": "tasks",
    "sort_by": "level",
    "capacity_warn_pct": 80,
    "show_prompt_preview": True,
    "highlight_alerts": True,
    "auto_open_busy": False,
    "default_layout": "catalog",
    "sound_on_alert": False,
    "show_cost_in_cards": True,
    "pin_role_ids": [],
    "filter_min_level": 0,
    "filter_max_level": 4,
    "timezone": "Asia/Taipei",
    "show_on_call_only": False,
}
