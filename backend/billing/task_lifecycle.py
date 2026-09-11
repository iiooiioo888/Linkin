"""任務計費生命週期：estimate → reserve → snapshot → bind key → settle。"""
from __future__ import annotations

import uuid
from typing import Any

from backend.billing.key_binding import get_task_key, select_and_bind_key
from backend.billing.pool_store import get_pool_store
from backend.billing.pools_service import get_pools_service


def begin_billed_task(
    user_id: str,
    *,
    task_id: str | None = None,
    baseline_tokens: int = 1000,
    iterations: int = 1,
    roles: int = 1,
    model: str = "default",
    org_id: str | None = None,
) -> dict[str, Any]:
    tid = task_id or f"task_{uuid.uuid4().hex[:16]}"
    pools = get_pools_service()
    reserve = pools.reserve_for_task(
        user_id,
        tid,
        baseline_tokens=baseline_tokens,
        iterations=iterations,
        roles=roles,
        model=model,
    )
    binding = select_and_bind_key(
        tid,
        estimate_credits=reserve["reserved_credits"],
        model=model,
        org_id=org_id,
    )
    return {**reserve, **binding}


def record_llm_usage(
    task_id: str,
    *,
    input_tokens: int,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    model: str = "default",
    role: str = "",
    tool: str = "",
    key_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_pools_service().settle_task_usage(
        task_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        model=model,
        role=role,
        tool=tool,
        key_id=key_id or get_task_key(task_id),
        meta=meta,
    )


def complete_billed_task(task_id: str) -> dict[str, Any]:
    store = get_pool_store()
    with store._conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_credits), 0) AS total FROM pool_usage_events WHERE task_id=?",
            (task_id,),
        ).fetchone()
    actual = float(row["total"]) if row else 0.0
    return get_pools_service().finalize_task(task_id, actual)
