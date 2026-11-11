"""角色 Agent 監控聚合：每位公司角色一張獨立工作台。

資料來源（唯讀、降級安全）：
- role_catalog：內建角色 + 自定義角色 + 設定覆蓋
- task_manager：即時公司任務看板與事件
- company_runs JSONL：歷史工作項與角色事件

TODO(多租戶)：seat_io／run log 歷史 ingest 尚未按 task.user_id 過濾，僅 live 任務已隔離。

每位角色視為一個 Agent：inbox 計數、指派任務列表、審查隊列、
事件時間軸。Manager / Reviewer / Synthesizer 除看板指派外，
另納入分解 / 審查 / 整合等協調型工作。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- common：logger、狀態集合、事件提示、時間與狀態 helper
- events：事件解析／壓縮／寫入
- items：工作項 ingest（kanban／spine／live task／run log）
- costs：token／成本統計、預算拆分、雲成本分配
- roster：空白 agent 卡與待命名冊
- aggregate：collect_agent_monitor 主聚合
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.company.raho.protocol import (
    canonical_role_id,
    grill_edges,
    raho_directory,
    role_to_raho_layer,
)
from backend.company.role_catalog import (
    LEVEL_LABELS,
    catalog_meta,
    get_monitor_prefs,
    list_role_snapshots,
)
from backend.company.run_log import DEFAULT_RUN_LOG_DIR
from backend.company.state import WorkItemStatus
from backend.services.task_manager import TaskRecord, task_manager

from .aggregate import collect_agent_monitor
from .common import (
    MAX_EVENTS_PER_ROLE,
    MAX_ITEMS_PER_ROLE,
    MAX_RUN_FILES,
    OPEN_STATUSES,
    PHASE_ROLE,
    ROLE_EVENT_HINTS,
    logger,
)
from .costs import (
    _allocate_cloud_costs,
    _apply_split_budgets,
    _count_budget_alerts,
    _finalize_agent,
    _limit_over,
    _limit_remaining,
)
from .roster import build_idle_roster

__all__ = [
    "DEFAULT_RUN_LOG_DIR",
    "LEVEL_LABELS",
    "MAX_EVENTS_PER_ROLE",
    "MAX_ITEMS_PER_ROLE",
    "MAX_RUN_FILES",
    "OPEN_STATUSES",
    "PHASE_ROLE",
    "ROLE_EVENT_HINTS",
    "Any",
    "Path",
    "TaskRecord",
    "WorkItemStatus",
    "_allocate_cloud_costs",
    "_apply_split_budgets",
    "_count_budget_alerts",
    "_finalize_agent",
    "_limit_over",
    "_limit_remaining",
    "annotations",
    "build_idle_roster",
    "canonical_role_id",
    "catalog_meta",
    "collect_agent_monitor",
    "datetime",
    "get_monitor_prefs",
    "grill_edges",
    "json",
    "list_role_snapshots",
    "logger",
    "logging",
    "os",
    "raho_directory",
    "role_to_raho_layer",
    "task_manager",
    "timezone",
]
