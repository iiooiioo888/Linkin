"""統一計量閘道：所有計費事件匯入 usage_events 並扣積分。"""

from __future__ import annotations

import logging
from typing import Any

from backend.billing.context import billing_enabled, current_billing_task, current_billing_user
from backend.billing.credits import (
    credits_for_docker_usd,
    credits_for_llm_tokens,
    credits_for_mc_fill,
    credits_for_mc_op,
    credits_for_opc_read,
    credits_for_opc_write,
    credits_for_quant_call,
    credits_for_raho_layer,
    credits_for_reflection_iteration,
    credits_for_recall,
)
from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
from backend.billing.plans import PACK_ADVANCED_MODELS, PACK_MINECRAFT, PACK_OPC, PACK_QUANT, PACK_RAHO, plan_has_feature
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
    payload = dict(meta or {})
    payload["event_type"] = event_type
    if not skip_debit:
        svc.debit_credits(uid, amount, source=event_type, reference=reference or event_type, meta=payload)
    event = svc.store.add_usage_event(
        uid, event_type, amount, quantity=quantity, unit=unit, task_id=tid, reference=reference, meta=payload
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
) -> dict | None:
    uid = _user(user_id)
    if uid:
        acct = get_billing_service().ensure_account(uid)
        from backend.billing.credits import model_multiplier

        if model_multiplier(model) >= 2.0 and not plan_has_feature(acct["plan_id"], PACK_ADVANCED_MODELS):
            if not acct.get("byok"):
                raise FeatureNotEntitledError(feature=PACK_ADVANCED_MODELS, plan_id=acct["plan_id"])
    credits = credits_for_llm_tokens(model, input_tokens, output_tokens)
    m = dict(meta or {})
    m.update({"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens})
    return emit_usage_event("llm_tokens", credits, user_id=uid, task_id=task_id, reference=reference, meta=m, quantity=input_tokens + output_tokens, unit="token")


def precheck_llm(model: str, input_tokens: int, output_tokens: int, *, user_id: str | None = None) -> None:
    if not billing_enabled() and not user_id:
        return
    uid = _user(user_id)
    if not uid:
        return
    est = credits_for_llm_tokens(model, input_tokens, output_tokens) * ESTIMATE_BUFFER
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
    return emit_usage_event(
        "docker_runtime",
        credits,
        quantity=hours,
        unit="hour",
        reference=service,
        meta={"service": service, "cost_usd": cost_usd},
        **kwargs,
    )


def meter_recall(**kwargs) -> dict | None:
    return emit_usage_event("integrations_recall", credits_for_recall(), reference="recall", **kwargs)
