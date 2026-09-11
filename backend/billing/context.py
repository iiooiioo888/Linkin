"""計費上下文（contextvars）。"""

from __future__ import annotations

import contextvars
import os

billing_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("billing_user_id", default="")
billing_task_id: contextvars.ContextVar[str] = contextvars.ContextVar("billing_task_id", default="")
billing_skipped: contextvars.ContextVar[bool] = contextvars.ContextVar("billing_skipped", default=False)


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
