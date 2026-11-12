"""同步推論與 Agent 任務編排。只透過 backend.core.llm.call_llm 發模型請求。

套件化：本模組已拆為 backend/hub/service/ 套件，公開 import 路徑不變。
failover／probe／complete／agents／auth 各自持有領域函式；本 __init__.py 只做 re-export，
並保留 from backend.core.llm import call_llm 作為測試 patch 表面（子模組經 _compat 延遲解析）。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from backend.core.llm import call_llm
from backend.hub.budget_guard import actual_cost_usd, estimate_cost_usd, estimate_tokens
from backend.hub.cache import semantic_key, should_bypass_cache
from backend.hub.catalog import (
    ALLOWED_STRATEGIES,
    ALLOWED_TOOLS,
    HUB_CATALOG,
    QUALITY_FLAGSHIP,
    is_forbidden_model_string,
    provider_of,
    runtime_hub_whitelist,
    validate_model_id,
)
from backend.hub.errors import (
    MSG_ALL_DOWN,
    MSG_BUDGET,
    MSG_EGRESS,
    MSG_FAILOVER_OK,
    MSG_FILTER,
    MSG_TIMEOUT,
    MSG_UNSUPPORTED,
    HubError,
)
from backend.hub.router import (
    CONNECT_TIMEOUT_S,
    HubUpstreamError,
    Metrics,
    agent_synthesis_chain,
    default_metrics,
    invoke_with_failover,
    pick_primary,
    race_sync,
    race_to_the_top,
)
from backend.hub.runtime import runtime
from backend.hub.safety import contains_sensitive, content_is_multimodal, flatten_messages_text
from backend.hub.store import AgentTask, HubUser, new_chat_id, new_task_id, new_trace_id
from backend.hub.tools import infer_tools, invoke_tool, tool_arguments

from .agents import (
    create_agent_task,
    get_agent_task,
    run_agent_task,
)
from .auth import (
    authenticate,
)
from .complete import (
    complete_chat,
    race_first_token,
)
from .failover import (
    _validate_messages,
    parse_failover_config,
)
from .probe import (
    _llm_probe,
    _record_circuit,
)

__all__ = [
    "ALLOWED_STRATEGIES",
    "ALLOWED_TOOLS",
    "CONNECT_TIMEOUT_S",
    "HUB_CATALOG",
    "MSG_ALL_DOWN",
    "MSG_BUDGET",
    "MSG_EGRESS",
    "MSG_FAILOVER_OK",
    "MSG_FILTER",
    "MSG_TIMEOUT",
    "MSG_UNSUPPORTED",
    "QUALITY_FLAGSHIP",
    "AgentTask",
    "Any",
    "Callable",
    "HubError",
    "HubUpstreamError",
    "HubUser",
    "Metrics",
    "_llm_probe",
    "_record_circuit",
    "_validate_messages",
    "actual_cost_usd",
    "agent_synthesis_chain",
    "authenticate",
    "call_llm",
    "complete_chat",
    "contains_sensitive",
    "content_is_multimodal",
    "create_agent_task",
    "default_metrics",
    "estimate_cost_usd",
    "estimate_tokens",
    "flatten_messages_text",
    "get_agent_task",
    "infer_tools",
    "invoke_tool",
    "invoke_with_failover",
    "is_forbidden_model_string",
    "json",
    "new_chat_id",
    "new_task_id",
    "new_trace_id",
    "parse_failover_config",
    "pick_primary",
    "provider_of",
    "race_first_token",
    "race_sync",
    "race_to_the_top",
    "run_agent_task",
    "runtime",
    "runtime_hub_whitelist",
    "semantic_key",
    "should_bypass_cache",
    "time",
    "tool_arguments",
    "validate_model_id",
]

# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.hub.service) 的公開名稱與原模組一致（55 個）。
for _submodule in (
    "_compat",
    "agents",
    "auth",
    "complete",
    "failover",
    "probe",
):
    globals().pop(_submodule, None)
del _submodule

