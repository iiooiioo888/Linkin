"""靈境·服務器運維域層：具名工具編排、人工批准隊列與 LLM 運維智能體（AIOps）。

三層模式對照 Minecraft MCP（AGENTS.md 鐵律）：
    backend/tools/server_admin.py   底層橋接（psutil/docker/systemd + 護欄 + 乾跑 + 審計）
    backend/linkin/server_admin.py  本檔：批准隊列、LLM 規劃、巡檢、日報、公司工具掛載
    backend/linkin/api.py           REST：/linkin/server/*

核心紀律：
- **絕不暴露自由 shell**——只有具名工具白名單（底層 ALL_TOOLS）
- 寫操作一律先產生 ``pending_approval``，管理員確認後才執行；
  ``auto_approve`` 需要環境變數 ``EVOL_SA_AUTO_APPROVE=true`` 雙重開關才生效
- LLM 經 backend.core.llm.call_llm（AGENTS.md #1）；無金鑰/失敗時降級關鍵詞路由
- 批准隊列 JSON 持久化（EVOL_SA_PENDING_PATH），TTL 過期自動作廢

環境變數：
    EVOL_SA_PENDING_PATH      批准隊列路徑（默認 backend/data/linkin/server_pending.json）
    EVOL_SA_PENDING_TTL_MIN   批准有效期分鐘（默認 30，1–1440）
    EVOL_SA_AUTO_APPROVE      允許 API 的 auto_approve 直接執行（默認 false）
    EVOL_SA_NO_LLM            強制關閉 LLM 規劃（關鍵詞路由兜底）
    EVOL_SA_MODEL             規劃模型（默認走 stage_router 的 generate 層級）
    EVOL_SA_DISK_WARN         巡檢磁盤告警閾值 %（默認 80）

套件化：本模組已拆為 backend/linkin/server_admin/ 套件，公開 import 路徑不變。
config／pending／tools／agent 各自持有領域內容，本 __init__.py 只做 re-export。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.core.llm import call_llm
from backend.tools import server_admin as sa
from backend.tools.server_admin import ServerAdminError

from .agent import (
    _INT_PARAMS,
    _PARAM_KEYS,
    SA_SYSTEM_PROMPT,
    _extract_json,
    _llm_ready,
    _plan_keyword,
    _plan_with_llm,
    _sanitize_params,
    ask_agent,
    audit_tail,
    daily_report,
    health_snapshot,
    patrol,
)
from .config import (
    _TRUE,
    DEFAULT_PENDING_PATH,
    DEFAULT_TTL_MIN,
    PENDING_KEEP_DAYS,
    _env_flag,
    _env_int,
    logger,
    pending_path,
)
from .pending import (
    _get_pending_or_raise,
    _is_expired,
    _load_pending,
    _lock,
    _pending_cache,
    _pending_mtime,
    _save_pending,
    _ttl_min,
    cancel_approval,
    confirm_approval,
    create_approval,
    list_approvals,
    reset_cache,
)
from .tools import (
    _COMPANY_TOOL_NAMES,
    _KEYWORD_ROUTES,
    _SERVICE_HINTS,
    _WRITE_ROLES,
    TOOL_CATALOG,
    execute_for_agent,
    execute_tool,
    register_company_tools,
)

__all__ = [
    "DEFAULT_PENDING_PATH",
    "DEFAULT_TTL_MIN",
    "PENDING_KEEP_DAYS",
    "SA_SYSTEM_PROMPT",
    "TOOL_CATALOG",
    "_COMPANY_TOOL_NAMES",
    "_INT_PARAMS",
    "_KEYWORD_ROUTES",
    "_PARAM_KEYS",
    "_SERVICE_HINTS",
    "_TRUE",
    "_WRITE_ROLES",
    "Any",
    "Path",
    "ServerAdminError",
    "_env_flag",
    "_env_int",
    "_extract_json",
    "_get_pending_or_raise",
    "_is_expired",
    "_llm_ready",
    "_load_pending",
    "_lock",
    "_pending_cache",
    "_pending_mtime",
    "_plan_keyword",
    "_plan_with_llm",
    "_sanitize_params",
    "_save_pending",
    "_ttl_min",
    "ask_agent",
    "audit_tail",
    "call_llm",
    "cancel_approval",
    "confirm_approval",
    "create_approval",
    "daily_report",
    "execute_for_agent",
    "execute_tool",
    "health_snapshot",
    "json",
    "list_approvals",
    "logger",
    "logging",
    "os",
    "patrol",
    "pending_path",
    "re",
    "register_company_tools",
    "reset_cache",
    "sa",
    "threading",
    "time",
    "uuid",
]

# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.linkin.server_admin) 的公開名稱與原模組一致（33 個）。
for _submodule in (
    "agent",
    "config",
    "pending",
    "tools",
):
    globals().pop(_submodule, None)
del _submodule

