"""API 路由的資料模型：id/策略正規化、provider routing、模型清單與預設值常數（自 backend.core.api_router 抽出）。"""

from __future__ import annotations

import re
from typing import Any

from backend.core.llm_config import get_runtime_config
from backend.core.provider_pool import (
    KIND_LABELS,
    TOKEN_PLAN_LABEL,
    classify_provider,
    is_forbidden_model,
    is_token_plan_url,
    normalize_catalog_models,
    static_catalog,
)

ROUTE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
PRIMARY_ROUTE_ID = "primary"

ROUTE_STRATEGIES = frozenset(
    {"role_preferred", "weighted_round_robin", "random", "failover", "least_loaded"}
)


MODEL_TOKEN_HINTS: dict[str, dict[str, int]] = {
    "qwen-turbo": {"max_context": 131072, "max_output": 8192},
    "qwen-plus": {"max_context": 131072, "max_output": 16384},
    "qwen-max": {"max_context": 131072, "max_output": 16384},
    "qwen-long": {"max_context": 1_000_000, "max_output": 32768},
    "qwen3.8-max": {"max_context": 1_000_000, "max_output": 65536},
    "qwen3.8-flash": {"max_context": 1_000_000, "max_output": 65536},
    "qwen3.7-plus": {"max_context": 1_000_000, "max_output": 32768},
    "qwen3.7-flash": {"max_context": 1_000_000, "max_output": 32768},
    "qwen3.5-max": {"max_context": 131072, "max_output": 16384},
    "qwen3-coder-plus": {"max_context": 131072, "max_output": 16384},
    "qwen-vl-plus": {"max_context": 131072, "max_output": 8192},
    "qwen-vl-max": {"max_context": 131072, "max_output": 8192},
    "qwen-omni-turbo": {"max_context": 131072, "max_output": 8192},
    "deepseek-v4-flash": {"max_context": 128000, "max_output": 8192},
    "deepseek-v4-pro": {"max_context": 128000, "max_output": 8192},
    "deepseek-v4-flash-vision-exp": {"max_context": 128000, "max_output": 8192},
    "kimi-k2": {"max_context": 128000, "max_output": 8192},
    "kimi-k3": {"max_context": 1_000_000, "max_output": 16384},
    "kimi-k2.7-code": {"max_context": 256000, "max_output": 16384},
    "kimi-k2.6": {"max_context": 256000, "max_output": 16384},
    "moonshot-v1-8k": {"max_context": 8192, "max_output": 4096},
    "moonshot-v1-32k": {"max_context": 32768, "max_output": 8192},
    "moonshot-v1-128k": {"max_context": 128000, "max_output": 8192},
    "gpt-4o": {"max_context": 128000, "max_output": 16384},
    "gpt-4o-mini": {"max_context": 128000, "max_output": 16384},
    "gpt-4.1": {"max_context": 1047576, "max_output": 32768},
    "gpt-4.1-mini": {"max_context": 1047576, "max_output": 32768},
    "gpt-4.1-nano": {"max_context": 1047576, "max_output": 16384},
    "gemini-3.1-pro": {"max_context": 1048576, "max_output": 65536},
    "gemini-3.1-flash": {"max_context": 1048576, "max_output": 32768},
    "gpt-6-astra": {"max_context": 1_050_000, "max_output": 128000},
    "gpt-5.6-sol": {"max_context": 1_050_000, "max_output": 128000},
    "gpt-5.6-terra": {"max_context": 1_050_000, "max_output": 128000},
    "gpt-5.6-luna": {"max_context": 1_050_000, "max_output": 128000},
    "glm-4-flash": {"max_context": 128000, "max_output": 8192},
    "glm-4": {"max_context": 128000, "max_output": 8192},
    "glm-4-plus": {"max_context": 128000, "max_output": 16384},
    "glm-5": {"max_context": 200000, "max_output": 128000},
    "glm-5.1": {"max_context": 200000, "max_output": 128000},
    "glm-5.2": {"max_context": 1_000_000, "max_output": 128000},
    "glm-5.3": {"max_context": 1_000_000, "max_output": 128000},
    "glm-5.3-flash": {"max_context": 1_000_000, "max_output": 128000},
    "mimo-v2.5-pro": {"max_context": 128000, "max_output": 8192},
    "mercury-2": {"max_context": 128000, "max_output": 8192},
    "nemotron-3.5-lightning": {"max_context": 128000, "max_output": 8192},
}


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "token-plan": {
        "name": TOKEN_PLAN_LABEL,
        "api_base": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.8-flash",
    },
    "qwen": {
        "name": "通義千問 Qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.8-flash",
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_base": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "moonshot": {
        "name": "Moonshot / Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "model": "kimi-k3",
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_base": "https://openrouter.ai/api/v1",
        "model": "",
    },
    "openai": {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-5.6-terra",
    },
    "zhipu": {
        "name": "智譜 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.3",
    },
    "ollama": {
        "name": "Ollama（本地）",
        "api_base": "http://127.0.0.1:11434/v1",
        "model": "",
    },
}


def _bare(model: str) -> str:
    text = (model or "").strip()
    if not text:
        return ""
    return text.split("/")[-1].lower()


def _model_in_list(requested: str, allowed: list[str]) -> str | None:
    req = (requested or "").strip()
    if not req or is_forbidden_model(req):
        return None
    allowed_l = [a.strip() for a in allowed if a and not is_forbidden_model(a)]
    if req in allowed_l:
        return req
    bare = _bare(req)
    for item in allowed_l:
        if item == req or _bare(item) == bare:
            return item
    return None


def _normalize_provider_routing(raw: Any) -> dict[str, Any] | None:
    """OpenRouter Provider Routing：sort / only / order / allow_fallbacks。"""
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, Any] = {}
    sort = str(raw.get("sort") or "").strip().lower()
    if sort in {"price", "latency", "throughput"}:
        out["sort"] = sort
    only = raw.get("only") if raw.get("only") is not None else raw.get("allowed_providers")
    if isinstance(only, str):
        only = [part.strip() for part in only.split(",") if part.strip()]
    if isinstance(only, list):
        cleaned = [str(item).strip() for item in only if str(item).strip()]
        if cleaned:
            out["only"] = cleaned
    order = raw.get("order")
    if isinstance(order, str):
        order = [part.strip() for part in order.split(",") if part.strip()]
    if isinstance(order, list):
        cleaned = [str(item).strip() for item in order if str(item).strip()]
        if cleaned:
            out["order"] = cleaned
    if raw.get("allow_fallbacks") is not None:
        out["allow_fallbacks"] = bool(raw.get("allow_fallbacks"))
    return out or None


def _sanitize_route_id(value: str, fallback: str = "") -> str:
    text = (value or "").strip().lower().replace(" ", "-")
    text = re.sub(r"[^a-z0-9_-]", "", text)
    if ROUTE_ID_RE.match(text):
        return text
    if fallback and ROUTE_ID_RE.match(fallback):
        return fallback
    return ""


def normalize_strategy(value: Any, fallback: str = "role_preferred") -> str:
    text = str(value or fallback).strip().lower()
    return text if text in ROUTE_STRATEGIES else fallback


def get_route_strategy(cfg: dict[str, Any] | None = None) -> str:
    runtime = cfg or get_runtime_config()
    return normalize_strategy(runtime.get("route_strategy"), "role_preferred")


def _default_models_for(provider: str, model: str) -> list[str]:
    rows = static_catalog(provider)
    ids = [r["id"] for r in rows]
    if model and model not in ids and not is_forbidden_model(model):
        ids = [model, *ids]
    return ids


def _token_plan_route_name(current: str) -> bool:
    text = (current or "").strip()
    if not text:
        return True
    qwen_preset = PROVIDER_PRESETS.get("qwen", {})
    return text in {
        str(qwen_preset.get("name") or ""),
        KIND_LABELS.get("qwen", ""),
        "通義千問 Qwen",
        "qwen",
    }


def normalize_route(raw: dict[str, Any] | None, *, existing_ids: set[str] | None = None) -> dict[str, Any]:
    """正規化一條路由；缺欄位時用供應商預設補齊。"""
    source = dict(raw or {})
    api_base = str(source.get("api_base") or "").strip()
    catalog_url = str(source.get("catalog_url") or "").strip()
    model = str(source.get("model") or "").strip()
    provider = str(source.get("provider") or "").strip().lower()
    if provider in {"kimi", "kimi-k2"}:
        provider = "moonshot"
    token_plan = is_token_plan_url(api_base) or is_token_plan_url(catalog_url)
    if token_plan:
        provider = "token-plan"
    elif not provider or provider == "custom":
        provider = classify_provider(api_base, model)
    preset = PROVIDER_PRESETS.get(provider, {})
    if not api_base:
        api_base = str(preset.get("api_base") or "")
    if not model:
        model = str(preset.get("model") or "")

    requested_id = _sanitize_route_id(str(source.get("id") or ""), provider or "route")
    taken = existing_ids or set()
    route_id = requested_id or provider or "route"
    if route_id in taken:
        suffix = 2
        base = route_id
        while f"{base}-{suffix}" in taken:
            suffix += 1
        route_id = f"{base}-{suffix}"

    allowed = [
        str(x).strip()
        for x in (source.get("allowed_models") or source.get("models") or [])
        if str(x).strip() and not is_forbidden_model(str(x))
    ]
    if not allowed:
        allowed = _default_models_for(provider, model)
    if model and not _model_in_list(model, allowed) and allowed:
        model = allowed[0]
    elif model and model not in allowed and not is_forbidden_model(model):
        allowed = [model, *allowed]

    raw_catalog = source.get("catalog_models") or [
        {"id": mid, "name": mid, "owned_by": provider} for mid in allowed
    ]
    catalog = normalize_catalog_models(
        list(raw_catalog) if isinstance(raw_catalog, list) else [],
        route_provider=provider,
    )
    try:
        weight = max(1, min(100, int(source.get("weight") or 10)))
    except (TypeError, ValueError):
        weight = 10

    routing = _normalize_provider_routing(source.get("provider_routing"))

    name = str(source.get("name") or preset.get("name") or KIND_LABELS.get(provider, provider)).strip()
    if token_plan and _token_plan_route_name(name):
        name = TOKEN_PLAN_LABEL
    return {
        "id": route_id,
        "name": name[:64] or route_id,
        "provider": provider,
        "api_key": str(source.get("api_key") or "").strip(),
        "api_base": api_base,
        "model": model,
        "allowed_models": allowed,
        "catalog_models": catalog[:200] if isinstance(catalog, list) else [],
        "catalog_source": str(source.get("catalog_source") or ""),
        "catalog_error": str(source.get("catalog_error") or ""),
        "catalog_fetched_at": str(source.get("catalog_fetched_at") or ""),
        "catalog_url": str(source.get("catalog_url") or ""),
        "weight": weight,
        "enabled": bool(source.get("enabled", True)),
        "fallback": bool(source.get("fallback", False)),
        "is_default": bool(source.get("is_default", False)),
        "models_locked": bool(source.get("models_locked", False)),
        "provider_routing": routing,
    }
