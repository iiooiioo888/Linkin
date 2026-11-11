"""API 路由的 provider presets、token hint 與對外公開視圖（自 backend.core.api_router 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.core.llm_config import get_runtime_config, masked_key
from backend.core.provider_pool import (
    KIND_LABELS,
    MODEL_FAMILY_LABELS,
    TOKEN_PLAN_LABEL,
    infer_model_family,
)

from .models import MODEL_TOKEN_HINTS, PROVIDER_PRESETS, _bare, get_route_strategy
from .routes import get_default_route, list_routes, union_allowed_models


def token_hint_for(model: str) -> dict[str, int] | None:
    text = (model or "").strip()
    if not text:
        return None
    hit = MODEL_TOKEN_HINTS.get(text) or MODEL_TOKEN_HINTS.get(_bare(text))
    return dict(hit) if hit else None


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


def _route_provider_label(route: dict[str, Any]) -> str:
    provider = str(route.get("provider") or "")
    if provider == "token-plan":
        return TOKEN_PLAN_LABEL
    return KIND_LABELS.get(provider, provider)


def _build_models_by_provider(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for route in routes:
        provider = str(route.get("provider") or "")
        route_label = str(route.get("name") or route.get("id") or "")
        provider_label = _route_provider_label(route)
        allowed = [str(x) for x in (route.get("allowed_models") or []) if str(x).strip()]
        catalog = list(route.get("catalog_models") or [])
        if provider == "token-plan":
            families: dict[str, list[str]] = {}
            for item in catalog:
                if isinstance(item, dict):
                    mid = str(item.get("id") or "").strip()
                    if not mid:
                        continue
                    family = str(item.get("owned_by") or infer_model_family(mid))
                    families.setdefault(family, []).append(mid)
            if not families and allowed:
                for mid in allowed:
                    family = infer_model_family(mid)
                    families.setdefault(family, []).append(mid)
            for family, models in sorted(families.items()):
                family_label = MODEL_FAMILY_LABELS.get(family, family)
                rows.append(
                    {
                        "route_id": route.get("id") or "",
                        "name": f"{route_label} · {family_label}",
                        "provider": provider,
                        "provider_label": provider_label,
                        "family": family,
                        "enabled": bool(route.get("enabled", True)),
                        "models": models,
                    }
                )
            continue
        rows.append(
            {
                "route_id": route.get("id") or "",
                "name": route_label,
                "provider": provider,
                "provider_label": provider_label,
                "enabled": bool(route.get("enabled", True)),
                "models": allowed,
            }
        )
    return rows


def public_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": route.get("id") or "",
        "name": route.get("name") or "",
        "provider": route.get("provider") or "",
        "provider_label": _route_provider_label(route),
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
    except Exception:
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
        "models_by_provider": _build_models_by_provider(routes),
    }
