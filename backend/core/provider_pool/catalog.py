"""模型目錄：HTTP 抓取、payload 解析、正規化與 refresh 系列。

fetch_catalog／refresh_model_catalog 直接以本模組的 _http_get_json 發請求，
測試 patch 目標為 backend.core.provider_pool.catalog._http_get_json。
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .constants import CRAWL_KINDS, DEFAULT_REFRESH_SEC, logger
from .helpers import (
    _model_in_pool,
    _now_iso,
    classify_provider,
    friendly_model_name,
    infer_model_family,
    is_forbidden_model,
    models_endpoint,
    static_catalog,
)


def normalize_catalog_model(
    item: dict[str, str] | str,
    *,
    route_provider: str = "",
) -> dict[str, str]:
    if isinstance(item, str):
        mid = item.strip()
        owned = infer_model_family(mid) if route_provider == "token-plan" else route_provider
        name = friendly_model_name(mid) if route_provider == "token-plan" else mid
        return {"id": mid, "name": name, "owned_by": owned}
    mid = str(item.get("id") or item.get("name") or "").strip()
    owned = str(item.get("owned_by") or item.get("canonical_slug") or "").strip()
    name = str(item.get("name") or mid).strip()
    if route_provider == "token-plan":
        if not owned or owned in {"system", "token-plan"}:
            owned = infer_model_family(mid)
        if name == mid or not name:
            name = friendly_model_name(mid)
    elif not owned:
        owned = route_provider
    return {"id": mid, "name": name or mid, "owned_by": owned}


def normalize_catalog_models(
    models: list[Any],
    *,
    route_provider: str = "",
) -> list[dict[str, str]]:
    if route_provider != "token-plan":
        return [
            normalize_catalog_model(item, route_provider=route_provider)
            for item in models
            if isinstance(item, (str, dict))
        ]
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, (str, dict)):
            continue
        row = normalize_catalog_model(item, route_provider="token-plan")
        mid = row.get("id") or ""
        if not mid or is_forbidden_model(mid) or mid.lower() in seen:
            continue
        seen.add(mid.lower())
        out.append(row)
    return out


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


def parse_models_payload(
    payload: dict[str, Any],
    *,
    route_provider: str = "",
) -> list[dict[str, str]]:
    rows = payload.get("data") or payload.get("models") or payload.get("data".upper())
    if rows is None and isinstance(payload.get("id"), str):
        rows = [payload]
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in rows:
        if isinstance(item, (str, dict)):
            row = normalize_catalog_model(item, route_provider=route_provider)
        else:
            continue
        mid = row.get("id") or ""
        name = row.get("name") or mid
        if not mid or is_forbidden_model(mid) or is_forbidden_model(name):
            continue
        key = mid.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def refresh_interval_sec(cfg: dict[str, Any] | None = None) -> int:
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    try:
        interval = runtime.get("ops_refresh_interval_sec") or os.getenv(
            "EVOL_LLM_OPS_INTERVAL_SEC", DEFAULT_REFRESH_SEC
        )
        raw = int(interval) if interval is not None else DEFAULT_REFRESH_SEC
    except (TypeError, ValueError):
        raw = DEFAULT_REFRESH_SEC
    return max(60, min(3600, raw))


def _is_auth_catalog_error(error: str) -> bool:
    """爬取目錄時的金鑰／授權失敗（不應因靜態回退而標為健康）。 """
    e = (error or "").lower()
    return (
        "401" in e
        or "403" in e
        or "unauthorized" in e
        or "invalid api key" in e
        or "incorrect api key" in e
        or "authentication" in e
        or "api key" in e and ("invalid" in e or "missing" in e)
    )


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
            models = parse_models_payload(payload, route_provider=kind)
            if models:
                source = "crawl"
            else:
                error = "目錄為空，改用靜態清單"
        except Exception as exc:
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
    auth_error = _is_auth_catalog_error(error)
    ok = not auth_error and (
        source == "crawl" or (source in {"static", "configured"} and bool(allowed))
    )
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
        "auth_error": auth_error,
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

    from .registry import public_pool  # 延遲匯入：避免 catalog ↔ registry 循環依賴

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
            "ops_last_error": "" if ok else (catalog["catalog_error"] or ""),
            "ops_last_latency_ms": catalog["elapsed_ms"],
            "ops_consecutive_fail": 0 if ok else int(cfg.get("ops_consecutive_fail") or 0) + 1,
        }
    )
    try:
        from backend.core.api_router import (
            PRIMARY_ROUTE_ID,
            list_routes,
            save_routes,
            sync_primary_into_routes,
        )

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
    except Exception:
        logger.warning("額外 API 路由目錄刷新失敗", exc_info=True)
    return public_pool()
