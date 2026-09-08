"""多 API / 多模型路由器。

在單一 llm_config 之上允許同時保存多組供應商憑證（千問、DeepSeek、
Kimi、OpenRouter…），依策略或角色偏好把請求分發到對應端點與模型。

向後相容：未設定 api_routes 時，把頂層 api_key / api_base / model
合成一條 id=primary 的路由，既有單一廠商鎖定行為不變。
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from backend.core.llm_config import get_runtime_config, masked_key, merge_runtime_config
from backend.core.provider_pool import (
    KIND_LABELS,
    classify_provider,
    is_forbidden_model,
    static_catalog,
)

logger = logging.getLogger(__name__)

ROUTE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
PRIMARY_ROUTE_ID = "primary"

ROUTE_STRATEGIES = frozenset(
    {"role_preferred", "weighted_round_robin", "random", "failover", "least_loaded"}
)

# 角色設定滑桿用的建議上限（非硬限制；實際仍以供應商為準）
MODEL_TOKEN_HINTS: dict[str, dict[str, int]] = {
    "qwen-turbo": {"max_context": 131072, "max_output": 8192},
    "qwen-plus": {"max_context": 131072, "max_output": 16384},
    "qwen-max": {"max_context": 131072, "max_output": 16384},
    "qwen-long": {"max_context": 1_000_000, "max_output": 32768},
    "qwen3.5-max": {"max_context": 131072, "max_output": 16384},
    "qwen3-coder-plus": {"max_context": 131072, "max_output": 16384},
    "qwen-vl-plus": {"max_context": 131072, "max_output": 8192},
    "qwen-vl-max": {"max_context": 131072, "max_output": 8192},
    "deepseek-v4-flash": {"max_context": 128000, "max_output": 8192},
    "deepseek-v4-pro": {"max_context": 128000, "max_output": 8192},
    "deepseek-v4-flash-vision-exp": {"max_context": 128000, "max_output": 8192},
    "kimi-k2": {"max_context": 128000, "max_output": 8192},
    "kimi-k3": {"max_context": 256000, "max_output": 16384},
    "moonshot-v1-8k": {"max_context": 8192, "max_output": 4096},
    "moonshot-v1-32k": {"max_context": 32768, "max_output": 8192},
    "moonshot-v1-128k": {"max_context": 128000, "max_output": 8192},
    "gpt-4o": {"max_context": 128000, "max_output": 16384},
    "gpt-4o-mini": {"max_context": 128000, "max_output": 16384},
    "gpt-4.1": {"max_context": 1047576, "max_output": 32768},
    "gpt-4.1-mini": {"max_context": 1047576, "max_output": 32768},
    "gpt-4.1-nano": {"max_context": 1047576, "max_output": 16384},
    "gpt-5.6-sol": {"max_context": 200000, "max_output": 32768},
    "gemini-3.1-pro": {"max_context": 1048576, "max_output": 65536},
    "glm-4-flash": {"max_context": 128000, "max_output": 8192},
    "glm-4": {"max_context": 128000, "max_output": 8192},
    "glm-4-plus": {"max_context": 128000, "max_output": 16384},
    "glm-5.2": {"max_context": 128000, "max_output": 16384},
    "mimo-v2.5-pro": {"max_context": 128000, "max_output": 8192},
    "mercury-2": {"max_context": 128000, "max_output": 8192},
    "nemotron-3.5-lightning": {"max_context": 128000, "max_output": 8192},
}


def token_hint_for(model: str) -> dict[str, int] | None:
    text = (model or "").strip()
    if not text:
        return None
    hit = MODEL_TOKEN_HINTS.get(text) or MODEL_TOKEN_HINTS.get(_bare(text))
    return dict(hit) if hit else None


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "qwen": {
        "name": "通義千問 Qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_base": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "moonshot": {
        "name": "Moonshot / Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "model": "kimi-k2",
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_base": "https://openrouter.ai/api/v1",
        "model": "",
    },
    "openai": {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
    "zhipu": {
        "name": "智譜 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "ollama": {
        "name": "Ollama（本地）",
        "api_base": "http://127.0.0.1:11434/v1",
        "model": "",
    },
}

_lock = threading.Lock()
_wrr_current: dict[str, int] = {}
_inflight: dict[str, int] = {}


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


def provider_presets_public() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for kind, preset in PROVIDER_PRESETS.items():
        rows.append(
            {
                "id": kind,
                "name": preset["name"],
                "api_base": preset["api_base"],
                "model": preset["model"],
                "label": KIND_LABELS.get(kind, preset["name"]),
            }
        )
    rows.append(
        {
            "id": "custom",
            "name": "自訂（OpenAI 相容）",
            "api_base": "",
            "model": "",
            "label": KIND_LABELS.get("generic", "通用端點"),
        }
    )
    return rows


def _default_models_for(provider: str, model: str) -> list[str]:
    rows = static_catalog(provider)
    ids = [r["id"] for r in rows]
    if model and model not in ids and not is_forbidden_model(model):
        ids = [model, *ids]
    return ids


def normalize_route(raw: dict[str, Any] | None, *, existing_ids: set[str] | None = None) -> dict[str, Any]:
    """正規化一條路由；缺欄位時用供應商預設補齊。"""
    source = dict(raw or {})
    api_base = str(source.get("api_base") or "").strip()
    model = str(source.get("model") or "").strip()
    provider = str(source.get("provider") or "").strip().lower()
    if provider in {"kimi", "kimi-k2"}:
        provider = "moonshot"
    if not provider or provider == "custom":
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

    catalog = source.get("catalog_models") or [
        {"id": mid, "name": mid, "owned_by": provider} for mid in allowed
    ]
    try:
        weight = max(1, min(100, int(source.get("weight") or 10)))
    except (TypeError, ValueError):
        weight = 10

    routing = _normalize_provider_routing(source.get("provider_routing"))

    name = str(source.get("name") or preset.get("name") or KIND_LABELS.get(provider, provider)).strip()
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


def synthesize_primary_route(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """把頂層單一配置合成 primary 路由。"""
    runtime = cfg or get_runtime_config()
    api_base = str(runtime.get("api_base") or "")
    model = str(runtime.get("model") or "")
    kind = str(runtime.get("provider_kind") or classify_provider(api_base, model))
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    catalog = runtime.get("catalog_models") or []
    return normalize_route(
        {
            "id": PRIMARY_ROUTE_ID,
            "name": KIND_LABELS.get(kind, kind) or "預設 API",
            "provider": kind,
            "api_key": str(runtime.get("api_key") or ""),
            "api_base": api_base,
            "model": model,
            "allowed_models": allowed,
            "catalog_models": catalog,
            "catalog_source": str(runtime.get("catalog_source") or ""),
            "catalog_error": str(runtime.get("catalog_error") or ""),
            "catalog_fetched_at": str(runtime.get("catalog_fetched_at") or ""),
            "catalog_url": str(runtime.get("catalog_url") or ""),
            "weight": 10,
            "enabled": bool(runtime.get("api_key") or api_base),
            "fallback": False,
            "is_default": True,
        }
    )


def _raw_routes(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    runtime = cfg or get_runtime_config()
    rows = runtime.get("api_routes")
    if isinstance(rows, list) and rows:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            route = normalize_route(item, existing_ids=seen)
            seen.add(route["id"])
            out.append(route)
        if out:
            if not any(r.get("is_default") for r in out):
                out[0]["is_default"] = True
            return out
    has_catalog = bool(runtime.get("allowed_models") or runtime.get("catalog_models"))
    if str(runtime.get("api_base") or "").strip() or has_catalog:
        return [synthesize_primary_route(runtime)]
    return []


def list_routes(cfg: dict[str, Any] | None = None, *, include_disabled: bool = True) -> list[dict[str, Any]]:
    routes = _raw_routes(cfg)
    if include_disabled:
        return routes
    return [r for r in routes if r.get("enabled")]


def list_enabled_routes(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [r for r in list_routes(cfg) if r.get("enabled") and (r.get("api_key") or r.get("api_base"))]


def get_route(route_id: str, cfg: dict[str, Any] | None = None) -> dict[str, Any] | None:
    want = (route_id or "").strip().lower()
    if not want:
        return None
    for route in list_routes(cfg):
        if route["id"] == want:
            return route
    return None


def _alias_provider(value: str) -> str:
    text = (value or "").strip().lower()
    if text in {"kimi", "kimi-k2", "kimi-k3"}:
        return "moonshot"
    if text in {"tongyi", "dashscope", "aliyun"}:
        return "qwen"
    return text


def resolve_route_ref(ref: str | None, cfg: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """以路由 id 或供應商種類（qwen / deepseek / moonshot…）找出路由。"""
    want = _alias_provider(str(ref or ""))
    if not want:
        return None
    hit = get_route(want, cfg)
    if hit:
        return hit
    routes = list_enabled_routes(cfg) or list_routes(cfg)
    matches = [r for r in routes if _alias_provider(str(r.get("provider") or "")) == want]
    if not matches:
        return None
    default = get_default_route(cfg)
    if default and any(r["id"] == default["id"] for r in matches):
        return next(r for r in matches if r["id"] == default["id"])
    return matches[0]


def get_default_route(cfg: dict[str, Any] | None = None) -> dict[str, Any] | None:
    runtime = cfg or get_runtime_config()
    preferred = str(runtime.get("default_route_id") or "").strip().lower()
    routes = list_enabled_routes(runtime) or list_routes(runtime)
    if not routes:
        return None
    if preferred:
        hit = next((r for r in routes if r["id"] == preferred), None)
        if hit:
            return hit
    hit = next((r for r in routes if r.get("is_default")), None)
    return hit or routes[0]


def route_as_cfg(route: dict[str, Any]) -> dict[str, Any]:
    """把路由轉成 clamp_model / LiteLLM 可用的 runtime 片段。"""
    return {
        "api_key": route.get("api_key") or "",
        "api_base": route.get("api_base") or "",
        "model": route.get("model") or "",
        "provider_kind": route.get("provider") or "",
        "allowed_models": list(route.get("allowed_models") or []),
        "catalog_models": list(route.get("catalog_models") or []),
        "catalog_source": route.get("catalog_source") or "",
        "catalog_error": route.get("catalog_error") or "",
        "catalog_fetched_at": route.get("catalog_fetched_at") or "",
        "catalog_url": route.get("catalog_url") or "",
        "provider_routing": route.get("provider_routing"),
        "route_id": route.get("id") or "",
    }


def union_allowed_models(cfg: dict[str, Any] | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for route in list_enabled_routes(cfg) or list_routes(cfg):
        for mid in route.get("allowed_models") or []:
            key = str(mid).strip()
            if not key or key.lower() in seen:
                continue
            seen.add(key.lower())
            out.append(key)
    return out


def find_route_for_model(model: str, cfg: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """找出擁有該模型的路由；多條命中時優先預設路由。"""
    req = (model or "").strip()
    if not req:
        return None
    routes = list_enabled_routes(cfg) or list_routes(cfg)
    default = get_default_route(cfg)
    ranked = sorted(routes, key=lambda r: 0 if default and r["id"] == default["id"] else 1)
    for route in ranked:
        if _model_in_list(req, list(route.get("allowed_models") or [])):
            return route
        if _bare(req) and _bare(req) == _bare(str(route.get("model") or "")):
            return route
        if str(route.get("provider") or "") and _bare(req).startswith(str(route["provider"])):
            # 弱匹配：僅在該路由允許清單為空時使用
            if not route.get("allowed_models"):
                return route
    return None


def _persist_routes(routes: list[dict[str, Any]], *, default_id: str = "", strategy: str | None = None) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in routes:
        route = normalize_route(item, existing_ids=seen)
        seen.add(route["id"])
        cleaned.append(route)
    if not cleaned:
        fields: dict[str, Any] = {"api_routes": [], "default_route_id": ""}
        if strategy is not None:
            fields["route_strategy"] = normalize_strategy(strategy)
        merge_runtime_config(fields)
        return []

    chosen = (default_id or "").strip().lower()
    if chosen and any(r["id"] == chosen for r in cleaned):
        for route in cleaned:
            route["is_default"] = route["id"] == chosen
    elif not any(r.get("is_default") for r in cleaned):
        cleaned[0]["is_default"] = True
        chosen = cleaned[0]["id"]
    else:
        chosen = next(r["id"] for r in cleaned if r.get("is_default"))

    default = next((r for r in cleaned if r["id"] == chosen), cleaned[0])
    fields = {
        "api_routes": cleaned,
        "default_route_id": chosen,
        "api_key": default.get("api_key") or "",
        "api_base": default.get("api_base") or "",
        "model": default.get("model") or "",
        "provider_kind": default.get("provider") or "",
        "allowed_models": list(default.get("allowed_models") or []),
        "catalog_models": list(default.get("catalog_models") or []),
    }
    if strategy is not None:
        fields["route_strategy"] = normalize_strategy(strategy)
    merge_runtime_config(fields)
    return cleaned


def save_routes(routes: list[dict[str, Any]], *, strategy: str | None = None, default_id: str = "") -> list[dict[str, Any]]:
    return _persist_routes(routes, default_id=default_id, strategy=strategy)


def upsert_route(payload: dict[str, Any]) -> dict[str, Any]:
    routes = list_routes()
    raw_id = _sanitize_route_id(str(payload.get("id") or ""))
    taken = {r["id"] for r in routes}
    if raw_id and raw_id in taken:
        incoming = normalize_route(payload, existing_ids=set())
    else:
        incoming = normalize_route(payload, existing_ids=taken)
    keep_key = bool(payload.get("keep_api_key")) or not str(payload.get("api_key") or "").strip()
    replaced = False
    next_rows: list[dict[str, Any]] = []
    for route in routes:
        if route["id"] == incoming["id"]:
            if keep_key and not incoming.get("api_key"):
                incoming["api_key"] = route.get("api_key") or ""
            if "is_default" not in payload and "is_default" not in (payload or {}):
                incoming["is_default"] = bool(route.get("is_default"))
            elif payload.get("is_default") is None:
                incoming["is_default"] = bool(route.get("is_default"))
            next_rows.append(incoming)
            replaced = True
        else:
            if incoming.get("is_default"):
                route = {**route, "is_default": False}
            next_rows.append(route)
    if not replaced:
        if not next_rows:
            incoming["is_default"] = True
        next_rows.append(incoming)
    default_id = incoming["id"] if incoming.get("is_default") else ""
    saved = _persist_routes(next_rows, default_id=default_id)
    return next(r for r in saved if r["id"] == incoming["id"])


def delete_route(route_id: str) -> list[dict[str, Any]]:
    want = (route_id or "").strip().lower()
    routes = [r for r in list_routes() if r["id"] != want]
    return _persist_routes(routes)


def set_route_strategy(strategy: str) -> str:
    value = normalize_strategy(strategy)
    merge_runtime_config({"route_strategy": value})
    return value


def sync_primary_into_routes() -> None:
    """頂層 POST /config 儲存後，把 primary 寫回 api_routes。"""
    runtime = get_runtime_config()
    primary = synthesize_primary_route(runtime)
    if not (primary.get("api_key") or primary.get("api_base") or primary.get("model")):
        return
    routes = list(runtime.get("api_routes") or [])
    if not isinstance(routes, list) or not routes:
        _persist_routes([primary], default_id=PRIMARY_ROUTE_ID)
        return
    found = False
    next_rows: list[dict[str, Any]] = []
    for item in routes:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == PRIMARY_ROUTE_ID or (
            not found and bool(item.get("is_default"))
        ):
            merged = {
                **item,
                "api_key": primary.get("api_key") or item.get("api_key") or "",
                "api_base": primary.get("api_base") or item.get("api_base") or "",
                "model": primary.get("model") or item.get("model") or "",
                "allowed_models": primary.get("allowed_models") or item.get("allowed_models") or [],
                "catalog_models": primary.get("catalog_models") or item.get("catalog_models") or [],
                "provider": primary.get("provider") or item.get("provider") or "",
                "catalog_source": primary.get("catalog_source") or "",
                "catalog_error": primary.get("catalog_error") or "",
                "catalog_fetched_at": primary.get("catalog_fetched_at") or "",
                "is_default": True,
            }
            next_rows.append(merged)
            found = True
        else:
            next_rows.append({**item, "is_default": False} if found else item)
    if not found:
        primary["is_default"] = True
        next_rows.insert(0, primary)
    merge_runtime_config({"api_routes": next_rows, "default_route_id": PRIMARY_ROUTE_ID})


def _weighted_round_robin(routes: list[dict[str, Any]]) -> dict[str, Any]:
    with _lock:
        total = 0
        best: dict[str, Any] | None = None
        best_cur = -10**9
        for route in routes:
            rid = str(route["id"])
            weight = max(1, int(route.get("weight") or 1))
            _wrr_current[rid] = _wrr_current.get(rid, 0) + weight
            total += weight
            if _wrr_current[rid] > best_cur:
                best_cur = _wrr_current[rid]
                best = route
        if best is not None:
            _wrr_current[str(best["id"])] -= total
            return best
    return routes[0]


def _random_select(routes: list[dict[str, Any]]) -> dict[str, Any]:
    import random

    weights = [max(1, int(r.get("weight") or 1)) for r in routes]
    return random.choices(routes, weights=weights, k=1)[0]


def _least_loaded(routes: list[dict[str, Any]]) -> dict[str, Any]:
    """進行中請求最少者優先；並列時權重較高者優先。"""
    with _lock:
        return min(
            routes,
            key=lambda r: (
                int(_inflight.get(str(r.get("id") or ""), 0)),
                -max(1, int(r.get("weight") or 1)),
            ),
        )


def mark_route_start(route_id: str) -> None:
    rid = (route_id or "").strip()
    if not rid:
        return
    with _lock:
        _inflight[rid] = int(_inflight.get(rid) or 0) + 1


def mark_route_end(route_id: str) -> None:
    rid = (route_id or "").strip()
    if not rid:
        return
    with _lock:
        _inflight[rid] = max(0, int(_inflight.get(rid) or 0) - 1)


def route_inflight_snapshot() -> dict[str, int]:
    with _lock:
        return dict(_inflight)


def select_route(
    *,
    route_id: str | None = None,
    model: str | None = None,
    strategy: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """依角色指定 / 全域策略 / 模型歸屬挑一條路由。

    角色 `route_id` 永遠優先。`role_preferred` 依模型所屬 API；
    加權輪詢／隨機／最少負載會跨 API 分發（再 clamp 到該路由模型池）。
    """
    runtime = cfg or get_runtime_config()
    enabled = list_enabled_routes(runtime)
    if not enabled:
        enabled = list_routes(runtime)
    if not enabled:
        return None

    if route_id:
        hit = resolve_route_ref(route_id, runtime)
        if hit and hit.get("enabled", True):
            return hit

    chosen_strategy = normalize_strategy(strategy or get_route_strategy(runtime))
    if chosen_strategy == "role_preferred" and model:
        owned = find_route_for_model(model, runtime)
        if owned:
            return owned

    if chosen_strategy == "weighted_round_robin" and len(enabled) > 1:
        return _weighted_round_robin(enabled)
    if chosen_strategy == "random" and len(enabled) > 1:
        return _random_select(enabled)
    if chosen_strategy == "least_loaded" and len(enabled) > 1:
        return _least_loaded(enabled)
    if chosen_strategy == "failover":
        primary = get_default_route(runtime)
        if primary and primary.get("enabled", True):
            return primary
        non_fallback = [r for r in enabled if not r.get("fallback")]
        return (non_fallback or enabled)[0]

    if model:
        owned = find_route_for_model(model, runtime)
        if owned:
            return owned
    return get_default_route(runtime) or enabled[0]


def list_failover_chain(
    *,
    route_id: str | None = None,
    model: str | None = None,
    extra_models: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """呼叫失敗時依序嘗試的路由：指定／預設 → 角色備援模型所屬 API → 標為備援 →（failover 策略）其餘。"""
    runtime = cfg or get_runtime_config()
    enabled = list_enabled_routes(runtime)
    if not enabled:
        enabled = list_routes(runtime)
    if not enabled:
        return []

    primary = select_route(route_id=route_id, model=model, cfg=runtime)
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(route: dict[str, Any] | None) -> None:
        if not route:
            return
        rid = str(route.get("id") or "")
        if not rid or rid in seen:
            return
        seen.add(rid)
        chain.append(route)

    _add(primary)
    for extra in extra_models or []:
        owned = find_route_for_model(str(extra), runtime)
        _add(owned)
    for route in enabled:
        if route.get("fallback"):
            _add(route)
    # 全域 failover 且未指定角色路由時，才把其餘 API 納入備援鏈
    if get_route_strategy(runtime) == "failover" and not route_id:
        for route in enabled:
            _add(route)
    return chain


def resolve_target(
    *,
    model: str | None = None,
    route_id: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解析此次呼叫要用的憑證與模型。"""
    from backend.core.provider_pool import clamp_model

    runtime = cfg or get_runtime_config()
    route = select_route(route_id=route_id, model=model, cfg=runtime)
    if route is None:
        fallback_model = clamp_model(model, cfg=runtime)
        return {
            "route": None,
            "route_id": "",
            "model": fallback_model,
            "api_key": str(runtime.get("api_key") or ""),
            "api_base": str(runtime.get("api_base") or ""),
            "provider": str(runtime.get("provider_kind") or ""),
            "provider_routing": None,
            "cfg": runtime,
        }
    route_cfg = route_as_cfg(route)
    resolved = clamp_model(model or str(route.get("model") or ""), cfg=route_cfg)
    return {
        "route": route,
        "route_id": route.get("id") or "",
        "model": resolved,
        "api_key": str(route.get("api_key") or ""),
        "api_base": str(route.get("api_base") or ""),
        "provider": str(route.get("provider") or ""),
        "provider_routing": route.get("provider_routing"),
        "cfg": route_cfg,
    }


def public_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": route.get("id") or "",
        "name": route.get("name") or "",
        "provider": route.get("provider") or "",
        "provider_label": KIND_LABELS.get(str(route.get("provider") or ""), str(route.get("provider") or "")),
        "api_key": masked_key(str(route.get("api_key") or "")),
        "configured": bool(route.get("api_key")),
        "api_base": route.get("api_base") or "",
        "model": route.get("model") or "",
        "allowed_models": list(route.get("allowed_models") or []),
        "catalog": list(route.get("catalog_models") or []),
        "catalog_source": route.get("catalog_source") or "",
        "catalog_error": route.get("catalog_error") or "",
        "catalog_fetched_at": route.get("catalog_fetched_at") or "",
        "catalog_url": route.get("catalog_url") or "",
        "weight": int(route.get("weight") or 10),
        "enabled": bool(route.get("enabled", True)),
        "fallback": bool(route.get("fallback", False)),
        "is_default": bool(route.get("is_default", False)),
        "models_locked": bool(route.get("models_locked", False)),
        "provider_routing": route.get("provider_routing"),
    }


def _public_rate_cards() -> dict[str, Any]:
    try:
        from backend.company.rate_card import public_rate_cards

        return public_rate_cards()
    except Exception:  # noqa: BLE001
        return {"models": [], "by_id": {}, "fields": []}


def public_router_state(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    runtime = cfg or get_runtime_config()
    routes = list_routes(runtime)
    default = get_default_route(runtime)
    return {
        "route_strategy": get_route_strategy(runtime),
        "default_route_id": (default or {}).get("id") or "",
        "strategies": [
            {"id": "role_preferred", "label": "角色指定優先"},
            {"id": "weighted_round_robin", "label": "加權輪詢"},
            {"id": "random", "label": "加權隨機"},
            {"id": "least_loaded", "label": "最少負載"},
            {"id": "failover", "label": "主備故障轉移"},
        ],
        "presets": provider_presets_public(),
        "api_routes": [public_route(r) for r in routes],
        "allowed_models": union_allowed_models(runtime),
        "model_token_hints": dict(MODEL_TOKEN_HINTS),
        "model_rate_cards": _public_rate_cards(),
        "models_by_provider": [
            {
                "route_id": r["id"],
                "name": r.get("name") or r["id"],
                "provider": r.get("provider") or "",
                "provider_label": KIND_LABELS.get(str(r.get("provider") or ""), str(r.get("provider") or "")),
                "enabled": bool(r.get("enabled", True)),
                "models": list(r.get("allowed_models") or []),
            }
            for r in routes
        ],
    }


def reset_router_state() -> None:
    """測試用：清空加權輪詢計數與進行中請求。"""
    with _lock:
        _wrr_current.clear()
        _inflight.clear()
