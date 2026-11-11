"""模型池常數：禁止模型、廠商靜態目錄／host、標籤與爬取參數。

自 backend.core.provider_pool 抽出的模組層常數；子模組與套件 __init__ 共用。
"""

from __future__ import annotations

import logging
import re

# 沿用原單檔模組名稱，維持日誌通道不變
logger = logging.getLogger("backend.core.provider_pool")


logger = logging.getLogger("backend.core.provider_pool")  # 沿用原單檔模組名稱

_clamp_warned: set[tuple[str, str]] = set()  # 節流：每個 (請求模型, 替代模型) 只記一次 INFO

FORBIDDEN_RE = re.compile(r"(?i)claude|anthropic|opus-|sonnet-|haiku-|fable")

VENDOR_STATIC: dict[str, tuple[str, ...]] = {
    "deepseek": (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
    ),
    "qwen": (
        "qwen3.8-max",
        "qwen3.8-flash",
        "qwen3.7-plus",
        "qwen3.7-flash",
        "qwen3-coder-plus",
        "qwen-long",
        "qwen-plus",
        "qwen-max",
        "qwen-turbo",
        "qwen-vl-plus",
        "qwen-vl-max",
        "qwen-omni-turbo",
    ),
    "moonshot": (
        "kimi-k3",
        "kimi-k2.7-code",
        "kimi-k2.6",
    ),
    "zhipu": ("glm-5.3", "glm-5.3-flash", "glm-5.2", "glm-5.1", "glm-5"),
    "mimo": ("mimo-v2.5-pro",),
    # 新模型在前（static_ids[0] 為未知模型的 fallback）；已退役的 gpt-4o/4.1
    # 保留在尾端，供舊配置 clamp 相容（上游測試契約仍引用 gpt-4o-mini）
    "openai": (
        "gpt-6-astra",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
    ),
}

VENDOR_HOSTS: tuple[tuple[str, str], ...] = (
    ("token-plan", "token-plan"),
    ("openrouter.ai", "openrouter"),
    ("api.deepseek.com", "deepseek"),
    ("dashscope.aliyuncs.com", "qwen"),
    ("dashscope-intl.aliyuncs.com", "qwen"),
    ("api.moonshot.cn", "moonshot"),
    ("api.moonshot.ai", "moonshot"),
    ("open.bigmodel.cn", "zhipu"),
    ("api.openai.com", "openai"),
)

TOKEN_PLAN_LABEL = "阿里雲 Token Plan"

KIND_LABELS: dict[str, str] = {
    "deepseek": "DeepSeek（單一廠商）",
    "qwen": "通義千問 Qwen（單一廠商）",
    "moonshot": "Moonshot / Kimi（單一廠商）",
    "zhipu": "智譜 GLM（單一廠商）",
    "mimo": "小米 MiMo（單一廠商）",
    "openai": "OpenAI",
    "openrouter": "OpenRouter（通用模型目錄）",
    "ollama": "Ollama（本地通用）",
    "token-plan": TOKEN_PLAN_LABEL,
    "generic": "OpenAI 相容通用端點",
}

MODEL_FAMILY_LABELS: dict[str, str] = {
    "qwen": "通義千問 Qwen",
    "deepseek": "DeepSeek",
    "zhipu": "智譜 GLM",
    "moonshot": "Moonshot / Kimi",
    "token-plan": TOKEN_PLAN_LABEL,
}

MODEL_FAMILY_PREFIX_RE = re.compile(
    r"^(?P<family>qwen|wan|deepseek|glm|kimi|moonshot)[-._]?",
    re.IGNORECASE,
)

CRAWL_KINDS = frozenset({"openrouter", "ollama", "generic", "openai", "token-plan"})
DEFAULT_REFRESH_SEC = 300
