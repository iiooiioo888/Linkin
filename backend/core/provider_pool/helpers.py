"""模型池 helper：時間／名稱正規化、廠商分類、端點、clamp 與 failover 開關。

純函式（無模組狀態），供 catalog／health／registry 共用。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .constants import (
    CRAWL_KINDS,
    FORBIDDEN_RE,
    MODEL_FAMILY_PREFIX_RE,
    VENDOR_HOSTS,
    VENDOR_STATIC,
    _clamp_warned,
    logger,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bare(model: str) -> str:
    text = (model or "").strip()
    if not text:
        return ""
    return text.split("/")[-1].lower()


def is_forbidden_model(model: str) -> bool:
    return bool(FORBIDDEN_RE.search(model or ""))


def is_token_plan_url(url: str = "") -> bool:
    return "token-plan" in (url or "").strip().lower()


def infer_model_family(model_id: str) -> str:
    """依模型 id 前綴推斷廠商家族（Token Plan 等多廠商目錄用）。"""
    bare = _bare(model_id)
    if not bare:
        return "token-plan"
    match = MODEL_FAMILY_PREFIX_RE.match(bare)
    if not match:
        return "token-plan"
    family = match.group("family").lower()
    if family in {"qwen", "wan"}:
        return "qwen"
    if family == "glm":
        return "zhipu"
    if family in {"kimi", "moonshot"}:
        return "moonshot"
    return family


def friendly_model_name(model_id: str) -> str:
    """可讀顯示名；wire id 不變。"""
    bare = _bare(model_id)
    if not bare:
        return model_id
    match = MODEL_FAMILY_PREFIX_RE.match(bare)
    vendor_label = ""
    rest = bare
    if match:
        family = match.group("family").lower()
        vendor_label = {
            "qwen": "Qwen",
            "wan": "Wan",
            "deepseek": "DeepSeek",
            "glm": "GLM",
            "kimi": "Kimi",
            "moonshot": "Moonshot",
        }.get(family, family.title())
        rest = bare[match.end() :].lstrip("-._")
    parts = [p for p in re.split(r"[-_]+", rest) if p]
    formatted: list[str] = []
    for part in parts:
        if re.match(r"^v?\d", part, re.IGNORECASE):
            formatted.append(part.upper() if part.lower().startswith("v") else part)
        else:
            formatted.append(part.capitalize())
    suffix = " ".join(formatted)
    if vendor_label and suffix:
        return f"{vendor_label} {suffix}"
    if vendor_label:
        return vendor_label
    return bare


def classify_provider(api_base: str = "", model: str = "") -> str:
    """依端點與模型名判斷供應商類型。"""
    base = (api_base or "").strip().lower()
    model_l = (model or "").strip().lower()
    host = (urlparse(base).hostname or "").lower() if base else ""

    if "11434" in base or host in {"localhost", "127.0.0.1"} and "11434" in base:
        return "ollama"
    if is_token_plan_url(base):
        return "token-plan"
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
    if model_l.startswith(("kimi", "moonshot")):
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
        key = (requested, fallback)
        if key not in _clamp_warned:
            if len(_clamp_warned) > 200:  # 防無界增長
                _clamp_warned.clear()
            _clamp_warned.add(key)
            logger.info("模型 %s 不在目前 API 可用池，改用 %s", requested, fallback)
        else:
            logger.debug("模型 %s 不在目前 API 可用池，改用 %s（重複）", requested, fallback)
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
        except Exception:
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
    except Exception:
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
