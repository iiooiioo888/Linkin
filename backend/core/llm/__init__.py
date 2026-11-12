"""LiteLLM 統一呼叫層（Task 0.3）。

負責模型設定、速率限制重試與回應解析，所有節點都透過
此模組呼叫 LLM，方便日後替換供應商或加入快取。

LLM 供應商參數（金鑰、端點、模型）優先讀取運行時
配置（llm_config，可透過 /config API 動態設定），
未設定時回退環境變數。

本檔案已於第十一輪重構拆為套件：對外仍以
from backend.core.llm import call_llm, call_llm_stream 等名稱匯入；
實作分散在 params／usage／completion／core／roles／stream／json_text 等模組，
內部呼叫一律經 _compat 延遲解析套件層屬性，既有 patch 表面全部維持有效。
"""

# 注意：原 llm.py 沒有 from __future__ import annotations；套件層也不加，
# 否則 dir() 會多出公開名稱 annotations（重構前基線沒有）。
import json  # noqa: F401
import logging
import re  # noqa: F401
import time  # noqa: F401

from dotenv import load_dotenv
from litellm import completion as _litellm_completion
from litellm.exceptions import APIError, RateLimitError  # noqa: F401

from backend.core.llm_cache import get_llm_cache  # noqa: F401
from backend.core.llm_config import get_runtime_config  # noqa: F401
from backend.core.provider_pool import (  # noqa: F401
    clamp_model,
    failover_models,
    invoke_with_pool_failover,
    pool_failover_enabled,
)

from .completion import _build_call_hops, _completion_once  # noqa: F401
from .core import _call_llm_core, _call_llm_on_route, call_llm  # noqa: F401
from .json_text import parse_json_response  # noqa: F401
from .params import (  # noqa: F401
    _THINK_RE,
    MAX_RETRIES,
    RETRY_BACKOFF_SECONDS,
    _delta_reasoning,
    _ensure_provider_prefix,
    _llm_params,
    _message_visible_text,
    _openrouter_extra,
    _resolve_call_target,
    _truncate_prompt,
    split_thinking,
)
from .roles import llm_kwargs_for_role  # noqa: F401
from .stream import call_llm_stream  # noqa: F401
from .usage import _usage_tokens, _wallet_bill_llm  # noqa: F401

load_dotenv()

logger = logging.getLogger(__name__)

# litellm completion 與子模組 completion.py 同名：重新綁定回函式（測試 patch 表面）
completion = _litellm_completion

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in ("core", "json_text", "params", "roles", "stream", "usage"):
    globals().pop(_submodule, None)
del _submodule
