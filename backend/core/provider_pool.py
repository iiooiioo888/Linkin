"""依已儲存的 API 鎖定可用模型池。

規則：
- 單一廠商端點（如 DeepSeek）：Agent 只能用該廠商模型，禁止落到 gpt-4o 預設。
- 通用 OpenAI 相容端點（OpenRouter / Ollama / vLLM）：GET /models 爬取目錄並寫入配置。
- 禁止 Claude / Anthropic 進入可用池。
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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
    ),
    "moonshot": (
        "kimi-k3",
        "kimi-k2.7-code",
        "kimi-k2.6",
    ),
    "zhipu": ("glm-5.3", "glm-5.3-flash", "glm-5.2", "glm-5.1", "glm-5"),
    "mimo": ("mimo-v2.5-pro",),
    "openai": ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
}

VENDOR_HOSTS: tuple[tuple[str, str], ...] = (
    ("openrouter.ai", "openrouter"),
    ("api.deepseek.com", "deepseek"),
    ("dashscope.aliyuncs.com", "qwen"),
    ("dashscope-intl.aliyuncs.com", "qwen"),
    ("api.moonshot.cn", "moonshot"),
    ("api.moonshot.ai", "moonshot"),
    ("open.bigmodel.cn", "zhipu"),
    ("api.openai.com", "openai"),
)

KIND_LABELS: dict[str, str] = {
    "deepseek": "DeepSeek（單一廠商）",
    "qwen": "通義千問 Qwen（單一廠商）",
    "moonshot": "Moonshot / Kimi（單一廠商）",
    "zhipu": "智譜 GLM（單一廠商）",
    "mimo": "小米 MiMo（單一廠商）",
    "openai": "OpenAI",
    "openrouter": "OpenRouter（通用模型目錄）",
    "ollama": "Ollama（本地通用）",
    "generic": "OpenAI 相容通用端點",
}

CRAWL_KINDS = frozenset({"openrouter", "ollama", "generic", "openai"})
DEFAULT_REFRESH_SEC = 300

# ── 模型池呼叫健康 / Failover（P1）────────────────────────────
POOL_FAILURE_THRESHOLD = int(os.getenv("EVOL_LLM_POOL_FAIL_THRESHOLD", "2"))
POOL_OPEN_DURATION_S = float(os.getenv("EVOL_LLM_POOL_OPEN_SEC", "60"))
_pool_health: dict[str, dict[str, Any]] = {}
_last_probe: dict[str, Any] = {
    "at": "",
    "ok": False,
    "latency_ms": 0,
    "reason": "",
    "mode": "catalog",
    "opened": [],
    "healed": [],
    "error": "",
    "enabled": True,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bare(model: str) -> str:
    text = (model or "").strip()
    if not text:
        return ""
    return text.split("/")[-1].lower()


def is_forbidden_model(model: str) -> bool:
    return bool(FORBIDDEN_RE.search(model or ""))


def classify_provider(api_base: str = "", model: str = "") -> str:
    """依端點與模型名判斷供應商類型。"""
    base = (api_base or "").strip().lower()
    model_l = (model or "").strip().lower()
    host = (urlparse(base).hostname or "").lower() if base else ""

    if "11434" in base or host in {"localhost", "127.0.0.1"} and "11434" in base:
        return "ollama"
    for needle, kind in VENDOR_HOSTS:
        if needle in host or needle in base:
            return kind
    if "openrouter" in base:
        return "openrouter"
    # 自訂 / 閘道端點優先當通用：依 GET /models 鎖定，不被目前模型名帶跑
    if base:
        return "generic"
    if model_l.startswith("deepseek") or "/deepseek" in model_l:
        return "deepseek"
    if "qwen" in model_l:
        return "qwen"
    if model_l.startswith("kimi") or model_l.startswith("moonshot"):
        return "moonshot"
    if model_l.startswith("glm"):
        return "zhipu"
    if model_l.startswith("mimo"):
        return "mimo"
    return "openai"


def models_endpoint(api_base: str, kind: str) -> str:
    """OpenAI 相容 GET /models URL。"""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        if kind == "openai":
            return "https://api.openai.com/v1/models"
        if kind == "deepseek":
            return "https://api.deepseek.com/v1/models"
        if kind == "openrouter":
            return "https://openrouter.ai/api/v1/models"
        if kind == "ollama":
            return "http://127.0.0.1:11434/v1/models"
        return ""
    if base.endswith("/models"):
        return base
    if base.endswith("/v1"):
        return f"{base}/models"
    if "/v1/" in base:
        return f"{base.rstrip('/')}/models"
    return f"{base}/v1/models"


def _http_get_json(url: str, api_key: str, timeout: float = 15.0) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "EvoLoop/1.0",
        "HTTP-Referer": "https://evoloop.local",
        "X-Title": "EvoLoop",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        if isinstance(data, list):
            return {"data": data}
        raise ValueError("模型目錄回應不是 JSON 物件")
    return data


def parse_models_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = payload.get("data") or payload.get("models") or payload.get("data".upper())
    if rows is None and isinstance(payload.get("id"), str):
        rows = [payload]
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in rows:
        if isinstance(item, str):
            mid = item.strip()
            owned = ""
            name = mid
        elif isinstance(item, dict):
            mid = str(item.get("id") or item.get("name") or "").strip()
            owned = str(item.get("owned_by") or item.get("canonical_slug") or "")
            name = str(item.get("name") or mid)
        else:
            continue
        if not mid or is_forbidden_model(mid) or is_forbidden_model(name):
            continue
        key = mid.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": mid, "name": name, "owned_by": owned})
    return out


def static_catalog(kind: str) -> list[dict[str, str]]:
    models = VENDOR_STATIC.get(kind, ())
    return [{"id": m, "name": m, "owned_by": kind} for m in models]


def _model_in_pool(requested: str, allowed: list[str]) -> str | None:
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


def _clamp_against(requested: str | None, runtime: dict[str, Any]) -> str:
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    fallback = (runtime.get("model") or "").strip() or (allowed[0] if allowed else "gpt-4o")
    if is_forbidden_model(fallback) and allowed:
        fallback = allowed[0]
    if not requested:
        return fallback if not is_forbidden_model(fallback) else (allowed[0] if allowed else "deepseek-v4-flash")
    hit = _model_in_pool(requested, allowed or ([fallback] if fallback else []))
    if hit:
        return hit
    if allowed:
        logger.info("模型 %s 不在目前 API 可用池，改用 %s", requested, fallback)
        return fallback if _model_in_pool(fallback, allowed) else allowed[0]
    kind = classify_provider(str(runtime.get("api_base") or ""), fallback)
    static_ids = [row["id"] for row in static_catalog(kind)]
    hit = _model_in_pool(requested, static_ids)
    if hit:
        return hit
    if static_ids:
        logger.info("模型 %s 不屬於 %s，改用 %s", requested, kind, static_ids[0])
        return static_ids[0]
    return fallback


def clamp_model(
    requested: str | None,
    *,
    cfg: dict[str, Any] | None = None,
    route_id: str | None = None,
) -> str:
    """把請求模型鎖在目前 API（或指定路由）能用的池內。

    配置多條 API 時，會先找擁有該模型的路由；找不到才回退預設路由。
    只配一組金鑰時行為與原本單一廠商鎖定相同。
    """
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    if cfg is None:
        try:
            from backend.core.api_router import (
                find_route_for_model,
                get_route,
                list_enabled_routes,
                route_as_cfg,
                union_allowed_models,
            )

            if route_id:
                route = get_route(route_id, runtime)
                if route:
                    return _clamp_against(requested, route_as_cfg(route))
            routes = list_enabled_routes(runtime)
            if len(routes) >= 2:
                if requested:
                    owned = find_route_for_model(requested, runtime)
                    if owned:
                        return _clamp_against(requested, route_as_cfg(owned))
                runtime = {
                    **runtime,
                    "allowed_models": union_allowed_models(runtime),
                }
        except Exception:  # noqa: BLE001 — 路由層失敗時回退單一池
            logger.debug("多 API 路由 clamp 回退單一池", exc_info=True)
    return _clamp_against(requested, runtime)


def compatible_hub_models(
    hub_ids: Iterable[str],
    provider_of: Mapping[str, str] | None = None,
) -> list[str]:
    """Hub 目錄與目前 API 可用池的交集。

    只存 DeepSeek 時只會留下 DeepSeek 列；OpenRouter 則依爬取目錄的廠商前綴對應。
    對不到任何一筆時回空清單，呼叫端應回退完整目錄並交給 clamp_model。
    """
    from backend.core.llm_config import get_runtime_config

    runtime = get_runtime_config()
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    try:
        from backend.core.api_router import union_allowed_models

        union = union_allowed_models(runtime)
        if union:
            allowed = union
    except Exception:  # noqa: BLE001
        pass
    kind = str(
        runtime.get("provider_kind")
        or classify_provider(str(runtime.get("api_base") or ""), str(runtime.get("model") or ""))
    )
    ids = [str(x) for x in hub_ids]
    if not allowed:
        return ids

    matched: list[str] = []
    for hid in ids:
        if _model_in_pool(hid, allowed):
            matched.append(hid)
            continue
        hb = _bare(hid)
        if any(hb and (_bare(a) == hb or hb in _bare(a) or _bare(a) in hb) for a in allowed):
            matched.append(hid)
            continue
        vendor = str((provider_of or {}).get(hid) or "")
        if vendor == kind and kind not in CRAWL_KINDS:
            matched.append(hid)
            continue
        if vendor:
            prefix = f"{vendor}/"
            if any(a.lower().startswith(prefix) or f"/{vendor}" in a.lower() for a in allowed):
                matched.append(hid)
    return matched


def refresh_interval_sec(cfg: dict[str, Any] | None = None) -> int:
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    try:
        raw = int(runtime.get("ops_refresh_interval_sec") or os.getenv("EVOL_LLM_OPS_INTERVAL_SEC", DEFAULT_REFRESH_SEC))
    except (TypeError, ValueError):
        raw = DEFAULT_REFRESH_SEC
    return max(60, min(3600, raw))


def fetch_catalog(
    api_base: str,
    api_key: str,
    current_model: str,
    kind: str = "",
) -> dict[str, Any]:
    """對單一端點爬取或回退靜態目錄（不寫入配置）。"""
    kind = kind or classify_provider(api_base, current_model)
    url = models_endpoint(api_base, kind)
    started = datetime.now(timezone.utc)
    error = ""
    source = "static"
    models: list[dict[str, str]] = []

    should_crawl = bool(url) and (kind in CRAWL_KINDS or bool(api_key and url))
    if should_crawl:
        try:
            payload = _http_get_json(url, api_key)
            models = parse_models_payload(payload)
            if models:
                source = "crawl"
            else:
                error = "目錄為空，改用靜態清單"
        except Exception as exc:  # noqa: BLE001 — 爬取失敗必須回退，不得中斷 Agent
            error = str(exc)[:300]
            logger.warning("爬取模型目錄失敗（%s %s）：%s", kind, url, error)

    if not models:
        models = static_catalog(kind)
        if models and source != "crawl":
            source = "static"
        if not models and current_model and not is_forbidden_model(current_model):
            models = [{"id": current_model, "name": current_model, "owned_by": kind}]
            source = "configured"

    allowed = [m["id"] for m in models]
    chosen = current_model
    if not _model_in_pool(chosen, allowed) and allowed:
        chosen = allowed[0]
        logger.info("預設模型 %s 不可用，改為 %s（provider=%s）", current_model, chosen, kind)

    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    ok = source == "crawl" or (source in {"static", "configured"} and bool(allowed))
    return {
        "provider": kind,
        "model": chosen,
        "allowed_models": allowed,
        "catalog_models": models[:200],
        "catalog_source": source,
        "catalog_fetched_at": _now_iso(),
        "catalog_error": error,
        "catalog_url": url,
        "elapsed_ms": elapsed_ms,
        "ok": ok,
    }


def _merge_catalog_into_route(route: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    allowed = list(catalog.get("allowed_models") or [])
    model = str(catalog.get("model") or route.get("model") or "")
    if route.get("models_locked"):
        prev = [str(x) for x in (route.get("allowed_models") or []) if str(x).strip()]
        kept = [m for m in prev if _model_in_pool(m, allowed)]
        if kept:
            allowed = kept
            if model and not _model_in_pool(model, kept):
                model = kept[0]
    return {
        **route,
        "provider": catalog.get("provider") or route.get("provider"),
        "model": model,
        "allowed_models": allowed,
        "models_locked": bool(route.get("models_locked")),
        "catalog_models": catalog.get("catalog_models") or route.get("catalog_models") or [],
        "catalog_source": catalog.get("catalog_source") or "",
        "catalog_error": catalog.get("catalog_error") or "",
        "catalog_fetched_at": catalog.get("catalog_fetched_at") or "",
        "catalog_url": catalog.get("catalog_url") or "",
    }


def refresh_route_catalog(route_id: str, *, reason: str = "manual") -> dict[str, Any]:
    """刷新單一 API 路由的模型目錄。"""
    from backend.core.api_router import get_route, public_route, upsert_route

    route = get_route(route_id)
    if route is None:
        raise KeyError(f"找不到 API 路由：{route_id}")
    catalog = fetch_catalog(
        str(route.get("api_base") or ""),
        str(route.get("api_key") or ""),
        str(route.get("model") or ""),
        str(route.get("provider") or ""),
    )
    updated = upsert_route({**_merge_catalog_into_route(route, catalog), "keep_api_key": True})
    logger.info("路由 %s 目錄已刷新（reason=%s, source=%s）", route_id, reason, catalog["catalog_source"])
    return public_route(updated)


def refresh_model_catalog(*, reason: str = "manual", route_id: str | None = None) -> dict[str, Any]:
    """爬取或回退靜態目錄，寫入 llm_config，並必要時修正預設模型。

    有多條 API 路由時會逐條刷新；route_id 指定則只刷新該路由。
    """
    from backend.core.llm_config import get_runtime_config, merge_runtime_config

    if route_id:
        refresh_route_catalog(route_id, reason=reason)
        return public_pool()

    cfg = get_runtime_config()
    catalog = fetch_catalog(
        str(cfg.get("api_base") or ""),
        str(cfg.get("api_key") or ""),
        str(cfg.get("model") or ""),
        str(cfg.get("provider_kind") or ""),
    )
    ok = bool(catalog["ok"])
    merge_runtime_config(
        {
            "model": catalog["model"],
            "provider_kind": catalog["provider"],
            "allowed_models": catalog["allowed_models"],
            "catalog_models": catalog["catalog_models"],
            "catalog_source": catalog["catalog_source"],
            "catalog_fetched_at": catalog["catalog_fetched_at"],
            "catalog_error": catalog["catalog_error"],
            "catalog_url": catalog["catalog_url"],
            "ops_last_reason": reason,
            "ops_last_ok_at": _now_iso() if ok else cfg.get("ops_last_ok_at") or "",
            "ops_last_error": catalog["catalog_error"],
            "ops_last_latency_ms": catalog["elapsed_ms"],
            "ops_consecutive_fail": 0 if ok else int(cfg.get("ops_consecutive_fail") or 0) + 1,
        }
    )
    try:
        from backend.core.api_router import PRIMARY_ROUTE_ID, list_routes, save_routes, sync_primary_into_routes

        sync_primary_into_routes()
        refreshed: list[dict[str, Any]] = []
        for route in list_routes():
            is_primary = route.get("id") == PRIMARY_ROUTE_ID or route.get("is_default")
            if is_primary:
                refreshed.append(_merge_catalog_into_route(route, catalog))
                continue
            if not route.get("enabled", True) or not (route.get("api_key") or route.get("api_base")):
                refreshed.append(route)
                continue
            extra_cat = fetch_catalog(
                str(route.get("api_base") or ""),
                str(route.get("api_key") or ""),
                str(route.get("model") or ""),
                str(route.get("provider") or ""),
            )
            refreshed.append(_merge_catalog_into_route(route, extra_cat))
        if refreshed:
            save_routes(refreshed)
    except Exception:  # noqa: BLE001 — 額外路由刷新失敗不得擋住主目錄
        logger.warning("額外 API 路由目錄刷新失敗", exc_info=True)
    return public_pool()


def public_pool(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    kind = str(runtime.get("provider_kind") or classify_provider(
        str(runtime.get("api_base") or ""), str(runtime.get("model") or "")
    ))
    fetched = str(runtime.get("catalog_fetched_at") or "")
    interval = refresh_interval_sec(runtime)
    stale = False
    if fetched:
        try:
            ts = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            stale = age > interval * 2
        except ValueError:
            stale = True
    else:
        stale = True
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    router_state: dict[str, Any] = {}
    try:
        from backend.core.api_router import public_router_state, union_allowed_models

        router_state = public_router_state(runtime)
        union = router_state.get("allowed_models") or union_allowed_models(runtime)
        if union:
            allowed = union
    except Exception:  # noqa: BLE001
        router_state = {}
    route_count = len(router_state.get("api_routes") or [])
    models = runtime.get("catalog_models") or [{"id": m, "name": m, "owned_by": kind} for m in allowed]
    if route_count >= 2:
        merged: list[dict[str, str]] = []
        seen: set[str] = set()
        for route in router_state.get("api_routes") or []:
            label = str(route.get("name") or route.get("id") or "")
            for item in route.get("catalog") or []:
                if isinstance(item, dict):
                    mid = str(item.get("id") or "").strip()
                    row = {
                        "id": mid,
                        "name": str(item.get("name") or mid),
                        "owned_by": str(item.get("owned_by") or route.get("provider") or ""),
                        "route_id": str(route.get("id") or ""),
                        "route_name": label,
                    }
                else:
                    mid = str(item).strip()
                    row = {"id": mid, "name": mid, "owned_by": str(route.get("provider") or ""), "route_id": str(route.get("id") or ""), "route_name": label}
                key = mid.lower()
                if not mid or key in seen:
                    continue
                seen.add(key)
                merged.append(row)
        if merged:
            models = merged
    return {
        "provider_kind": kind,
        "provider_label": KIND_LABELS.get(kind, kind),
        "single_vendor": route_count <= 1 and (
            (kind not in CRAWL_KINDS) or (kind == "openai" and not str(runtime.get("api_base") or ""))
        ),
        "lock_message": _lock_message(kind, allowed, route_count=route_count, router_state=router_state),
        "model": runtime.get("model") or "",
        "api_base": runtime.get("api_base") or "",
        "configured": bool(runtime.get("api_key")),
        "allowed_models": allowed,
        "route_strategy": router_state.get("route_strategy") or "role_preferred",
        "default_route_id": router_state.get("default_route_id") or "",
        "api_routes": router_state.get("api_routes") or [],
        "models_by_provider": router_state.get("models_by_provider") or [],
        "route_strategies": router_state.get("strategies") or [],
        "provider_presets": router_state.get("presets") or [],
        "model_token_hints": router_state.get("model_token_hints") or {},
        "model_rate_cards": router_state.get("model_rate_cards") or {},
        "catalog": models,
        "catalog_source": runtime.get("catalog_source") or "",
        "catalog_url": runtime.get("catalog_url") or "",
        "catalog_fetched_at": fetched,
        "catalog_error": runtime.get("catalog_error") or "",
        "ops": {
            "refresh_interval_sec": interval,
            "last_ok_at": runtime.get("ops_last_ok_at") or "",
            "last_error": runtime.get("ops_last_error") or "",
            "last_latency_ms": int(runtime.get("ops_last_latency_ms") or 0),
            "last_reason": runtime.get("ops_last_reason") or "",
            "consecutive_fail": int(runtime.get("ops_consecutive_fail") or 0),
            "stale": stale,
            "enabled": os.getenv("EVOL_LLM_OPS_ENABLED", "true").lower() not in {"0", "false", "no"},
            "next_check_at": _next_check_at(fetched, interval),
            "pool_failover": {
                "enabled": pool_failover_enabled(),
                "timeout_s": pool_failover_timeout_s(),
                "slow_call_s": pool_failover_slow_s(),
                "fail_threshold": POOL_FAILURE_THRESHOLD,
                "open_duration_s": POOL_OPEN_DURATION_S,
                "models": pool_health_snapshot(),
                "active_probe": pool_probe_snapshot(),
            },
        },
    }


def _next_check_at(fetched: str, interval: int) -> str:
    if not fetched:
        return ""
    try:
        ts = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        nxt = ts.astimezone(timezone.utc) + timedelta(seconds=interval)
        return nxt.isoformat()
    except ValueError:
        return ""


def _lock_message(
    kind: str,
    allowed: list[str],
    *,
    route_count: int = 0,
    router_state: dict[str, Any] | None = None,
) -> str:
    n = len(allowed)
    routes = list((router_state or {}).get("api_routes") or [])
    enabled = [r for r in routes if r.get("enabled") and r.get("configured")]
    if len(enabled) >= 2:
        names = "、".join(str(r.get("name") or r.get("id")) for r in enabled[:6])
        return f"已配置 {len(enabled)} 組 API（{names}），共 {n} 個可用模型；角色可各自指定供應商與模型"
    if kind == "openrouter":
        return f"OpenRouter 通用目錄：已載入 {n} 個可用模型（已排除 Claude）"
    if kind in CRAWL_KINDS:
        return f"通用端點已鎖定 {n} 個爬取模型；Agent 不得改用其他廠商"
    label = KIND_LABELS.get(kind, kind)
    return f"目前只配置了 {label}，Agent 只能使用該廠商模型（{n}）"


def set_refresh_interval(seconds: int) -> dict[str, Any]:
    from backend.core.llm_config import merge_runtime_config

    snapshot = merge_runtime_config({"ops_refresh_interval_sec": max(60, min(3600, int(seconds)))})
    return public_pool(snapshot)


def pool_failover_enabled() -> bool:
    return os.getenv("EVOL_LLM_POOL_FAILOVER", "true").lower() not in {"0", "false", "no"}


def pool_failover_timeout_s() -> float:
    try:
        return max(1.0, float(os.getenv("EVOL_LLM_FAILOVER_TIMEOUT", "30")))
    except (TypeError, ValueError):
        return 30.0


def pool_failover_slow_s() -> float:
    try:
        return max(1.0, float(os.getenv("EVOL_LLM_FAILOVER_SLOW_S", "10")))
    except (TypeError, ValueError):
        return 10.0


def _health_entry(model: str) -> dict[str, Any]:
    if model not in _pool_health:
        _pool_health[model] = {
            "failures": 0,
            "successes": 0,
            "open_until": 0.0,
            "last_error": "",
            "last_latency_ms": 0,
            "probe_open": False,
        }
    return _pool_health[model]


def pool_probe_enabled() -> bool:
    return os.getenv("EVOL_LLM_POOL_PROBE", "true").lower() not in {"0", "false", "no"}


def pool_probe_timeout_s() -> float:
    try:
        return max(0.5, float(os.getenv("EVOL_LLM_POOL_PROBE_TIMEOUT", "3")))
    except (TypeError, ValueError):
        return 3.0


def pool_probe_ping_enabled() -> bool:
    """是否對主模型發輕量 ping（較貴；預設關閉，只做 GET /models）。"""
    return os.getenv("EVOL_LLM_POOL_PROBE_PING", "false").lower() in {"1", "true", "yes"}


def pool_probe_snapshot() -> dict[str, Any]:
    snap = dict(_last_probe)
    snap.update(
        {
            "enabled": pool_probe_enabled(),
            "timeout_s": pool_probe_timeout_s(),
            "ping_enabled": pool_probe_ping_enabled(),
        }
    )
    return snap


def force_open_pool_model(model: str, error: str = "", *, from_probe: bool = True) -> None:
    """主動熔斷：不等待連續失敗閾值。"""
    import time

    entry = _health_entry(model)
    entry["failures"] = max(int(entry.get("failures") or 0), POOL_FAILURE_THRESHOLD)
    entry["open_until"] = time.monotonic() + POOL_OPEN_DURATION_S
    entry["probe_open"] = bool(from_probe)
    if error:
        entry["last_error"] = error[:200]
    logger.warning("模型池主動熔斷 %s：%s", model, error or "probe")


def heal_pool_model(model: str, *, only_probe: bool = True) -> bool:
    """恢復模型；預設只解除探活造成的熔斷，不覆蓋真實呼叫失敗。"""
    entry = _health_entry(model)
    if only_probe and not entry.get("probe_open"):
        return False
    entry["failures"] = 0
    entry["open_until"] = 0.0
    entry["probe_open"] = False
    entry["last_error"] = ""
    entry["successes"] = int(entry.get("successes") or 0) + 1
    return True


def record_pool_call(
    model: str,
    failed: bool,
    duration_s: float = 0.0,
    error: str = "",
) -> None:
    """記錄單次 LLM 呼叫結果，連續失敗達閾值則暫時熔斷該模型。"""
    import time

    entry = _health_entry(model)
    now = time.monotonic()
    entry["last_latency_ms"] = int(duration_s * 1000)
    slow = duration_s >= pool_failover_slow_s()
    if failed or slow:
        entry["failures"] = int(entry.get("failures") or 0) + 1
        entry["probe_open"] = False
        if error:
            entry["last_error"] = error[:200]
        if entry["failures"] >= POOL_FAILURE_THRESHOLD:
            entry["open_until"] = now + POOL_OPEN_DURATION_S
            logger.warning(
                "模型池熔斷 %s（連續失敗 %d 次，%.0fs 內跳過）",
                model,
                entry["failures"],
                POOL_OPEN_DURATION_S,
            )
    else:
        entry["successes"] = int(entry.get("successes") or 0) + 1
        entry["failures"] = max(0, int(entry.get("failures") or 0) - 1)
        if entry["failures"] == 0:
            entry["open_until"] = 0.0
            entry["last_error"] = ""
            entry["probe_open"] = False


def is_pool_model_open(model: str) -> bool:
    import time

    entry = _health_entry(model)
    return time.monotonic() < float(entry.get("open_until") or 0.0)


def pool_health_snapshot() -> dict[str, dict[str, Any]]:
    import time

    now = time.monotonic()
    out: dict[str, dict[str, Any]] = {}
    for model, entry in _pool_health.items():
        open_until = float(entry.get("open_until") or 0.0)
        out[model] = {
            "failures": int(entry.get("failures") or 0),
            "successes": int(entry.get("successes") or 0),
            "open": now < open_until,
            "open_for_sec": max(0.0, open_until - now) if now < open_until else 0.0,
            "last_error": entry.get("last_error") or "",
            "last_latency_ms": int(entry.get("last_latency_ms") or 0),
            "probe_open": bool(entry.get("probe_open")),
        }
    return out


def reset_pool_health() -> None:
    """測試用：清空進程內健康狀態。"""
    _pool_health.clear()
    _last_probe.update(
        {
            "at": "",
            "ok": False,
            "latency_ms": 0,
            "reason": "",
            "mode": "catalog",
            "opened": [],
            "healed": [],
            "error": "",
            "enabled": pool_probe_enabled(),
        }
    )


def probe_pool_health(
    *,
    reason: str = "schedule",
    ping_fn: Any | None = None,
) -> dict[str, Any]:
    """主動探活：預設 GET /models；可選對主模型發輕量 ping。

    - 端點不可用 → 主動熔斷目前主模型，讓 Failover 提前切備援
    - 目錄有回應但缺某模型 → 熔斷該模型
    - 探活成功 → 只解除 probe_open 熔斷（不覆蓋真實呼叫失敗）
    """
    import time

    from backend.core.llm_config import get_runtime_config

    if not pool_probe_enabled():
        _last_probe.update(
            {
                "at": _now_iso(),
                "ok": False,
                "latency_ms": 0,
                "reason": reason,
                "mode": "disabled",
                "opened": [],
                "healed": [],
                "error": "probe disabled",
                "enabled": False,
            }
        )
        return pool_probe_snapshot()

    runtime = get_runtime_config()
    api_base = str(runtime.get("api_base") or "")
    api_key = str(runtime.get("api_key") or "")
    primary = clamp_model(str(runtime.get("model") or ""), cfg=runtime)
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    kind = str(runtime.get("provider_kind") or classify_provider(api_base, primary))
    url = models_endpoint(api_base, kind)
    opened: list[str] = []
    healed: list[str] = []
    mode = "catalog"
    error = ""
    ok = False
    latency_ms = 0

    t0 = time.monotonic()
    catalog_ids: list[str] = []
    if url:
        try:
            payload = _http_get_json(url, api_key, timeout=pool_probe_timeout_s())
            catalog_ids = [row["id"] for row in parse_models_payload(payload)]
            latency_ms = int((time.monotonic() - t0) * 1000)
            ok = True
        except Exception as exc:  # noqa: BLE001 — 探活失敗不得中斷主流程
            latency_ms = int((time.monotonic() - t0) * 1000)
            error = f"endpoint:{exc}"[:300]
            force_open_pool_model(primary, error, from_probe=True)
            opened.append(primary)
            logger.warning("模型池探活失敗（%s）：%s", url, error)
    else:
        error = "no models endpoint"
        latency_ms = int((time.monotonic() - t0) * 1000)

    if ok and catalog_ids:
        for model in allowed or [primary]:
            if _model_in_pool(model, catalog_ids):
                if heal_pool_model(model, only_probe=True):
                    healed.append(model)
            else:
                # 目錄明確不含此模型 → 提前熔斷，避免用戶請求才失敗
                force_open_pool_model(model, "probe: missing from catalog", from_probe=True)
                opened.append(model)

    if ok and pool_probe_ping_enabled() and ping_fn is not None:
        mode = "catalog+ping"
        # 含已熔斷模型：主動 ping 才能恢復；仍限制前 2 個控制成本
        targets: list[str] = []
        for model in [primary, *allowed]:
            if model and model not in targets:
                targets.append(model)
            if len(targets) >= 2:
                break
        for model in targets:
            if model in opened:
                continue
            pt0 = time.monotonic()
            try:
                ping_fn(
                    prompt="ping",
                    system=None,
                    model=model,
                    max_retries=1,
                    timeout=pool_probe_timeout_s(),
                    max_tokens=8,
                )
                record_pool_call(model, False, time.monotonic() - pt0)
                # ping 成功可視為真實可用，解除任何熔斷
                heal_pool_model(model, only_probe=False)
                if model not in healed:
                    healed.append(model)
            except Exception as exc:  # noqa: BLE001
                force_open_pool_model(model, f"probe ping:{exc}", from_probe=True)
                opened.append(model)

    # 去重保序
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    _last_probe.update(
        {
            "at": _now_iso(),
            "ok": ok,
            "latency_ms": latency_ms,
            "reason": reason,
            "mode": mode,
            "opened": _uniq(opened),
            "healed": _uniq(healed),
            "error": error,
            "enabled": True,
        }
    )
    return pool_probe_snapshot()


def _model_cost_score(model: str) -> float:
    try:
        from backend.company.budget import get_model_costs

        costs = get_model_costs()
        bare = _bare(model)
        for key, prices in costs.items():
            if key == model or _bare(key) == bare:
                return float(prices[0]) + float(prices[1])
    except Exception:  # noqa: BLE001
        pass
    return 999.0


def failover_models(requested: str | None, cfg: dict[str, Any] | None = None) -> list[str]:
    """依可用池與健康狀態產生 Failover 鏈：首選 → 其餘（成本由低到高）。"""
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    if cfg is None:
        try:
            from backend.core.api_router import find_route_for_model, route_as_cfg

            owned = find_route_for_model(requested or str(runtime.get("model") or ""), runtime)
            if owned:
                runtime = route_as_cfg(owned)
                allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
        except Exception:  # noqa: BLE001
            pass
    primary = clamp_model(requested or str(runtime.get("model") or ""), cfg=runtime)
    if not allowed:
        return [primary]

    healthy_primary = primary if not is_pool_model_open(primary) else None
    others = [m for m in allowed if m != primary and not is_pool_model_open(m)]
    others.sort(key=_model_cost_score)
    chain: list[str] = []
    if healthy_primary:
        chain.append(healthy_primary)
    chain.extend(others)
    if not chain:
        return [primary, *others] if primary not in others else allowed
    return chain


def _should_failover(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"TimeoutError", "RateLimitError", "APIError"}:
        return True
    text = str(exc).lower()
    return any(token in text for token in ("429", "503", "timeout", "rate limit", "unavailable"))


def invoke_with_pool_failover(
    call_fn: Any,
    *,
    prompt: str,
    system: str | None = None,
    models: list[str],
    max_retries: int | None = None,
    **kwargs: Any,
) -> tuple[str, str, int]:
    """在模型池內依序嘗試，回傳 (text, used_model, hops)。"""
    import time

    hops = 0
    last_error: Exception | None = None
    per_model_timeout = pool_failover_timeout_s()
    retries = max(1, int(max_retries or 1))

    for model in models:
        if is_pool_model_open(model):
            hops += 1
            continue
        t0 = time.monotonic()
        try:
            result = call_fn(
                prompt=prompt,
                system=system,
                model=model,
                max_retries=retries,
                timeout=per_model_timeout,
                **kwargs,
            )
            record_pool_call(model, False, time.monotonic() - t0)
            return str(result), model, hops
        except Exception as exc:  # noqa: BLE001 — 需嘗試下一模型
            duration = time.monotonic() - t0
            record_pool_call(model, True, duration, str(exc))
            last_error = exc
            if _should_failover(exc) or duration >= per_model_timeout:
                hops += 1
                logger.warning(
                    "模型 %s 呼叫失敗（%.1fs），切換備援：%s",
                    model,
                    duration,
                    exc,
                )
                continue
            raise
    raise RuntimeError("模型池全部不可用") from last_error
