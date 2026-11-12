"""LLM 呼叫層（自 backend.core.llm 抽出）。

角色設定 → call_llm 參數轉換。
"""

from __future__ import annotations


def llm_kwargs_for_role(runtime: dict | None) -> dict:
    """把角色設定轉成 call_llm 參數（供應商、Token、溫度）。"""
    if not runtime:
        return {}
    out: dict = {}
    provider = str(runtime.get("preferred_provider") or "").strip()
    if provider:
        try:
            from backend.core.api_router import resolve_route_ref

            route = resolve_route_ref(provider)
            out["route_id"] = (route or {}).get("id") or provider
        except Exception:
            out["route_id"] = provider
    failover = [
        str(item).strip()
        for item in (runtime.get("failover_models") or [])
        if str(item).strip()
    ]
    if failover:
        out["role_failover_models"] = failover
    try:
        tokens = int(runtime.get("max_output_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    if tokens > 0:
        out["max_tokens"] = tokens
    if runtime.get("temperature") is not None:
        try:
            out["temperature"] = float(runtime["temperature"])
        except (TypeError, ValueError):
            pass
    ctx = runtime.get("context_window") or runtime.get("max_context_tokens")
    try:
        ctx_n = int(ctx or 0)
    except (TypeError, ValueError):
        ctx_n = 0
    if ctx_n > 0:
        out["max_context_tokens"] = ctx_n
    retries = runtime.get("max_retries")
    if retries is not None:
        try:
            out["max_retries"] = max(1, int(retries))
        except (TypeError, ValueError):
            pass
    return out
