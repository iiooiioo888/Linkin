"""統一計量閘道：所有計費事件匯入 usage_events 並扣積分。"""

from __future__ import annotations

import logging
from typing import Any

from backend.billing.context import (
    billing_enabled,
    chat_billing_acc,
    chat_session_id,
    current_billing_task,
    current_billing_user,
    record_chat_meter,
)
from backend.billing.credits import (
    credits_for_docker_usd,
    credits_for_mc_fill,
    credits_for_mc_op,
    credits_for_opc_read,
    credits_for_opc_write,
    credits_for_quant_call,
    credits_for_raho_layer,
    credits_for_recall,
    credits_for_reflection_iteration,
)
from backend.billing.errors import FeatureNotEntitledError
from backend.billing.plans import (
    PACK_ADVANCED_MODELS,
    PACK_MINECRAFT,
    PACK_OPC,
    PACK_QUANT,
    PACK_RAHO,
    plan_has_feature,
)
from backend.billing.quota import get_billing_service

logger = logging.getLogger(__name__)

ESTIMATE_BUFFER = float(__import__("os").getenv("LINKIN_BILLING_ESTIMATE_BUFFER", "1.2"))


def _user(user_id: str | None = None) -> str:
    return (user_id or current_billing_user() or "").strip()


def _task(task_id: str | None = None) -> str:
    return (task_id or current_billing_task() or "").strip()


def require_feature(feature: str, user_id: str | None = None) -> None:
    if not billing_enabled() and not user_id:
        return
    uid = _user(user_id)
    if not uid:
        return
    svc = get_billing_service()
    acct = svc.ensure_account(uid)
    if not plan_has_feature(acct["plan_id"], feature):
        raise FeatureNotEntitledError(feature=feature, plan_id=acct["plan_id"])


def emit_usage_event(
    event_type: str,
    credits: float,
    *,
    user_id: str | None = None,
    quantity: float = 1,
    unit: str = "credit",
    task_id: str | None = None,
    reference: str = "",
    meta: dict[str, Any] | None = None,
    skip_debit: bool = False,
    ledger_source: str | None = None,
) -> dict[str, Any] | None:
    """記錄 usage_event 並扣積分（fail-closed）。"""
    uid = _user(user_id)
    if not uid:
        return None
    if not billing_enabled() and not user_id:
        return None
    amount = round(max(0.0, float(credits)), 4)
    if amount <= 0:
        return None
    svc = get_billing_service()
    tid = _task(task_id)
    if not tid:
        sid = chat_session_id()
        if sid:
            tid = sid
    payload = dict(meta or {})
    payload["event_type"] = event_type
    if not skip_debit:
        svc.debit_credits(
            uid,
            amount,
            source=ledger_source or event_type,
            reference=reference or event_type,
            meta=payload,
        )
    event = svc.store.add_usage_event(
        uid, event_type, amount, quantity=quantity, unit=unit, task_id=tid, reference=reference, meta=payload
    )
    if event and chat_billing_acc.get() is not None:
        record_chat_meter(
            amount,
            pricing_version=payload.get("pricing_version"),
            cache_savings_credits=float(payload.get("cache_savings_credits") or 0),
            vendor_id=payload.get("vendor_id"),
            model=payload.get("model"),
            input_tokens=int(payload.get("input_tokens") or 0),
            output_tokens=int(payload.get("output_tokens") or 0),
            cache_read_tokens=int(payload.get("cache_read_tokens") or 0),
            cache_write_tokens=int(payload.get("cache_write_tokens") or 0),
            event_type=event_type,
        )
    return event


def meter_llm(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    user_id: str | None = None,
    task_id: str | None = None,
    reference: str = "call_llm",
    meta: dict | None = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cached_tokens: int = 0,
    l3_cache_hit: bool = False,
    cache_metadata_missing: bool = False,
    vendor_id: str | None = None,
    role: str = "",
    tool: str = "",
) -> dict | None:
    uid = _user(user_id)
    tid = _task(task_id)
    if uid:
        acct = get_billing_service().ensure_account(uid)
        from backend.billing.credits import model_multiplier

        if model_multiplier(model) >= 2.0 and not plan_has_feature(acct["plan_id"], PACK_ADVANCED_MODELS):
            if not acct.get("byok"):
                raise FeatureNotEntitledError(feature=PACK_ADVANCED_MODELS, plan_id=acct["plan_id"])
    from backend.billing.pool_store import get_pool_store
    from backend.billing.pricing_engine import compute_cost_credits

    pools = get_pool_store()
    if tid:
        snap = pools.get_task_snapshot(tid)
        if snap:
            config = snap.get("pricing_config", pools.active_pricing_config()["config"])
            credits = compute_cost_credits(
                config,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens or cached_tokens,
                cache_write_tokens=cache_write_tokens,
                role=role,
                tool=tool,
                vendor_id=vendor_id,
                cache_metadata_missing=cache_metadata_missing,
                l3_cache_hit=l3_cache_hit,
            )
            from backend.billing.task_lifecycle import record_llm_usage

            usage = record_llm_usage(
                tid,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens or cached_tokens,
                cache_write_tokens=cache_write_tokens,
                l3_cache_hit=l3_cache_hit,
                cache_metadata_missing=cache_metadata_missing,
                vendor_id=vendor_id,
                model=model,
                role=role,
                tool=tool,
                meta=meta,
            )
            billed = float(usage.get("cost_credits", credits))
            if chat_billing_acc.get() is not None:
                record_chat_meter(
                    billed,
                    pricing_version=usage.get("pricing_version"),
                    vendor_id=vendor_id,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read_tokens or cached_tokens,
                    cache_write_tokens=cache_write_tokens,
                    event_type="llm_tokens",
                )
            return {"credits": billed, "task_id": tid, "pricing_version": usage.get("pricing_version")}
    config = pools.active_pricing_config()["config"]
    credits = compute_cost_credits(
        config,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens or cached_tokens,
        cache_write_tokens=cache_write_tokens,
        role=role,
        tool=tool,
        vendor_id=vendor_id,
        cache_metadata_missing=cache_metadata_missing,
        l3_cache_hit=l3_cache_hit,
    )
    m = dict(meta or {})
    m.update(
        {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens or cached_tokens,
            "cache_write_tokens": cache_write_tokens,
            "pricing_version": pools.active_pricing_config()["version"],
        }
    )
    return emit_usage_event(
        "llm_tokens", credits, user_id=uid, task_id=tid, reference=reference, meta=m, quantity=input_tokens + output_tokens, unit="token"
    )


def precheck_llm(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    user_id: str | None = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cached_tokens: int = 0,
) -> None:
    if not billing_enabled() and not user_id:
        return
    uid = _user(user_id)
    if not uid:
        return
    from backend.billing.pool_store import get_pool_store
    from backend.billing.pricing_engine import compute_cost_credits

    config = get_pool_store().active_pricing_config()["config"]
    est = compute_cost_credits(
        config,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens or cached_tokens,
        cache_write_tokens=cache_write_tokens,
    ) * ESTIMATE_BUFFER
    get_billing_service().ensure_can_afford(uid, est)


def meter_reflection_iteration(count: int = 1, **kwargs) -> dict | None:
    return emit_usage_event(
        "reflection_iter",
        credits_for_reflection_iteration(count),
        quantity=count,
        unit="iteration",
        reference="reflection_loop",
        **kwargs,
    )


def meter_raho_layer(layer: str, **kwargs) -> dict | None:
    require_feature(PACK_RAHO, kwargs.get("user_id"))
    kwargs.setdefault("reference", f"raho_{layer}")
    meta = dict(kwargs.pop("meta", None) or {})
    meta["layer"] = layer
    return emit_usage_event("raho_role", credits_for_raho_layer(layer), meta=meta, **kwargs)


def meter_quant_call(count: int = 1, **kwargs) -> dict | None:
    require_feature(PACK_QUANT, kwargs.get("user_id"))
    kwargs.setdefault("reference", "quant")
    return emit_usage_event("quant_api", credits_for_quant_call(count), quantity=count, unit="call", **kwargs)


def meter_opc_write(count: int = 1, **kwargs) -> dict | None:
    require_feature(PACK_OPC, kwargs.get("user_id"))
    return emit_usage_event("opc_write", credits_for_opc_write(count), quantity=count, unit="write", reference="opc", **kwargs)


def meter_opc_read(count: int = 1, **kwargs) -> dict | None:
    require_feature(PACK_OPC, kwargs.get("user_id"))
    return emit_usage_event("opc_read", credits_for_opc_read(count), quantity=count, unit="read", reference="opc", **kwargs)


def meter_minecraft(tool: str, blocks: int = 0, **kwargs) -> dict | None:
    require_feature(PACK_MINECRAFT, kwargs.get("user_id"))
    credits = credits_for_mc_fill(blocks) if blocks > 0 or "fill" in tool.lower() else credits_for_mc_op(tool)
    return emit_usage_event("minecraft_op", credits, reference=tool, meta={"tool": tool, "blocks": blocks}, **kwargs)


def meter_docker(service: str, hours: float, cost_usd: float, **kwargs) -> dict | None:
    credits = credits_for_docker_usd(cost_usd)
    kwargs.setdefault("reference", f"docker:{service}")
    meta = dict(kwargs.pop("meta", None) or {})
    meta.update({"service": service, "cost_usd": cost_usd, "feature": "docker"})
    return emit_usage_event(
        "docker_runtime",
        credits,
        quantity=hours,
        unit="hour",
        ledger_source="docker",
        meta=meta,
        **kwargs,
    )


def meter_recall(**kwargs) -> dict | None:
    return emit_usage_event("integrations_recall", credits_for_recall(), reference="recall", **kwargs)
