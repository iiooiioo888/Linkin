"""API 路由的查詢／持久化／upsert 與主路由同步（自 backend.core.api_router 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.core.llm_config import get_runtime_config, merge_runtime_config
from backend.core.provider_pool import KIND_LABELS, classify_provider

from .models import (
    PRIMARY_ROUTE_ID,
    _bare,
    _model_in_list,
    _sanitize_route_id,
    normalize_route,
    normalize_strategy,
)


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
            if "is_default" not in payload and "is_default" not in (payload or {}) or payload.get("is_default") is None:
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
