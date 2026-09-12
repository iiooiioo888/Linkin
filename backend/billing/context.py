"""計費上下文（contextvars）。"""

from __future__ import annotations

import contextvars
import os

billing_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("billing_user_id", default="")
billing_task_id: contextvars.ContextVar[str] = contextvars.ContextVar("billing_task_id", default="")
billing_skipped: contextvars.ContextVar[bool] = contextvars.ContextVar("billing_skipped", default=False)
chat_billing_acc: contextvars.ContextVar[dict | None] = contextvars.ContextVar("chat_billing_acc", default=None)


def current_billing_user() -> str:
    return (billing_user_id.get() or "").strip()


def current_billing_task() -> str:
    return (billing_task_id.get() or "").strip()


def billing_enabled() -> bool:
    if billing_skipped.get():
        return False
    if os.getenv("LINKIN_BILLING_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("LINKIN_BILLING_FORCE", "").strip():
        return False
    return bool(current_billing_user())


def default_anonymous_user() -> str:
    return os.getenv("LINKIN_BILLING_ANONYMOUS_USER", "dev").strip() or "dev"


def begin_chat_billing(session_id: str = "") -> contextvars.Token:
    return chat_billing_acc.set(
        {
            "credits_deducted": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "call_count": 0,
            "models": [],
            "pricing_version": None,
            "cache_savings_credits": 0.0,
            "vendor_id": None,
            "session_id": (session_id or "").strip(),
            "interrupted": False,
            "interrupt_reason": "",
        }
    )


def end_chat_billing(token: contextvars.Token) -> None:
    chat_billing_acc.reset(token)


def chat_billing_snapshot() -> dict | None:
    acc = chat_billing_acc.get()
    if not acc:
        return None
    snap = dict(acc)
    models = snap.get("models")
    if isinstance(models, list):
        snap["models"] = list(models)
    return snap


def chat_session_id() -> str:
    acc = chat_billing_acc.get()
    if not acc:
        return ""
    return str(acc.get("session_id") or "").strip()


def record_chat_meter(
    credits: float,
    *,
    pricing_version: int | None = None,
    cache_savings_credits: float = 0.0,
    vendor_id: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    event_type: str = "",
) -> None:
    acc = chat_billing_acc.get()
    if acc is None:
        return
    acc["credits_deducted"] = round(float(acc.get("credits_deducted", 0)) + max(0.0, float(credits)), 4)
    if input_tokens:
        acc["input_tokens"] = int(acc.get("input_tokens", 0)) + int(input_tokens)
    if output_tokens:
        acc["output_tokens"] = int(acc.get("output_tokens", 0)) + int(output_tokens)
    if cache_read_tokens:
        acc["cache_read_tokens"] = int(acc.get("cache_read_tokens", 0)) + int(cache_read_tokens)
    if cache_write_tokens:
        acc["cache_write_tokens"] = int(acc.get("cache_write_tokens", 0)) + int(cache_write_tokens)
    if model:
        models = acc.setdefault("models", [])
        if model not in models:
            models.append(model)
    if event_type == "llm_tokens" or (input_tokens or output_tokens):
        acc["call_count"] = int(acc.get("call_count", 0)) + 1
    if pricing_version is not None:
        acc["pricing_version"] = pricing_version
    if cache_savings_credits:
        acc["cache_savings_credits"] = round(
            float(acc.get("cache_savings_credits", 0)) + float(cache_savings_credits), 4
        )
    if vendor_id:
        acc["vendor_id"] = vendor_id
