"""靈境 REST 路由：憲法、NPC、任務、道具、事件、總覽、運維與 grill-me。

第十二輪重構：實作已拆至本套件子模組（各領域 APIRouter 端點檔＋shared／router）；
此 __init__ 保留原模組層公開名稱（register_linkin／linkin_router／各端點函式等）
與既有 import 路徑，backend/main.py 的 from backend.linkin.api import register_linkin 不變。
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.linkin.constitution import (
    load_constitution,
    save_constitution,
    update_constitution,
)
from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_NPCS,
    COL_PLAYERS,
    COL_WORLDVIEW,
    QualityGateError,
    delete_entity,
    get_store,
    list_entities,
    upsert_entity,
)
from backend.linkin.tools import (
    TOOL_ITEM_CREATE,
    TOOL_NPC_CREATE,
    TOOL_NPC_DIALOGUE,
    TOOL_QUEST_GENERATE,
    ToolValidationError,
    format_npc_text,
    invoke_tool,
    npc_relationships,
)
from backend.tools.server_admin import ServerAdminError

from .constitution_routes import get_constitution, put_constitution
from .events import list_events
from .grill import grill_start, grill_status, grill_summary, grill_turn
from .items import create_item, list_items, remove_item
from .npcs import (
    create_npc,
    delete_npc_collection,
    list_npcs,
    npc_dialogue,
    remove_npc,
    update_npc,
    update_npc_collection,
)
from .overview import overview
from .quests import generate_quest, list_quests, remove_quest
from .router import linkin_router, register_linkin
from .server_routes import (
    server_approval_cancel,
    server_approval_confirm,
    server_approvals,
    server_ask,
    server_audit,
    server_health,
    server_patrol,
    server_report,
)
from .shared import logger

# 驗證指令友善別名：等價於 linkin_router（既有公開名稱為 linkin_router）
router = linkin_router

# 保留原 backend/linkin/api.py 的模組層公開名稱基線（dir() 非底線，63 個）＋
# 各領域端點函式；既有程式碼只 import register_linkin／linkin_router。
__all__ = [
    "COL_EVENTS",
    "COL_NPCS",
    "COL_PLAYERS",
    "COL_WORLDVIEW",
    "TOOL_ITEM_CREATE",
    "TOOL_NPC_CREATE",
    "TOOL_NPC_DIALOGUE",
    "TOOL_QUEST_GENERATE",
    "APIRouter",
    "Any",
    "HTTPException",
    "QualityGateError",
    "Query",
    "ServerAdminError",
    "ToolValidationError",
    "create_item",
    "create_npc",
    "delete_entity",
    "delete_npc_collection",
    "format_npc_text",
    "generate_quest",
    "get_constitution",
    "get_store",
    "grill_start",
    "grill_status",
    "grill_summary",
    "grill_turn",
    "invoke_tool",
    "json",
    "linkin_router",
    "list_entities",
    "list_events",
    "list_items",
    "list_npcs",
    "list_quests",
    "load_constitution",
    "logger",
    "logging",
    "npc_dialogue",
    "npc_relationships",
    "os",
    "overview",
    "put_constitution",
    "re",
    "register_linkin",
    "remove_item",
    "remove_npc",
    "remove_quest",
    "save_constitution",
    "server_approval_cancel",
    "server_approval_confirm",
    "server_approvals",
    "server_ask",
    "server_audit",
    "server_health",
    "server_patrol",
    "server_report",
    "update_constitution",
    "update_npc",
    "update_npc_collection",
    "upsert_entity",
    "uuid",
]
