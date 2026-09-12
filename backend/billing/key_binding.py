"""任務級 API Key 綁定 v6.0 Phase 2 — 共享池路由、健康追蹤、Failover。"""
from __future__ import annotations

import os
from typing import Any, Literal

from backend.billing.fault_pool import (
    record_cache_invalidation,
    record_degrade_spread,
    record_public_pool_premium,
)
from backend.billing.pool_store import get_pool_store
from backend.billing.routing import apply_routing_binding, route_key_selection

FailureKind = Literal["key_failure", "balance_exhausted"]


def _default_key_id() -> str:
    return os.environ.get("LINKIN_DEFAULT_API_KEY_ID", "platform_default")


def _resolve_account_for_task(task_id: str) -> tuple[str | None, str | None]:
    with get_pool_store()._conn() as conn:
        row = conn.execute("SELECT account_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return None, None
    account_id = str(row["account_id"])
    org_id = None
    with get_pool_store()._conn() as conn:
        urow = conn.execute("SELECT kyc_meta_json FROM users WHERE user_id=?", (account_id,)).fetchone()
        if urow and urow["kyc_meta_json"]:
            import json

            try:
                meta = json.loads(urow["kyc_meta_json"])
                org_id = meta.get("org_id")
            except json.JSONDecodeError:
                pass
    return account_id, org_id


def select_and_bind_key(
    task_id: str,
    *,
    estimate_credits: float,
    model: str = "default",
    account_id: str | None = None,
    org_id: str | None = None,
) -> dict[str, Any]:
    """
    Key 排序：quota≥est×1.3 → model → cache affinity → price → quality → concurrency → vendor routing weight
    Phase 2：共享池決策樹（single / same_org / relay / parallel / degrade / public / reject）。
    """
    aid = account_id
    oid = org_id
    if not aid:
        aid, oid = _resolve_account_for_task(task_id)

    if not aid:
        store = get_pool_store()
        store.bind_task_key(task_id, _default_key_id(), reason="fallback_no_account")
        return {
            "task_id": task_id,
            "key_id": _default_key_id(),
            "routing_mode": "single",
            "binding_reason": "fallback_no_account",
        }

    decision = route_key_selection(
        task_id=task_id,
        account_id=aid,
        model=model,
        estimate_credits=estimate_credits,
        org_id=oid,
    )
    result = apply_routing_binding(task_id, decision)
    if decision.get("routing_mode") == "degrade":
        record_degrade_spread(task_id, estimate_credits * 0.05, account_id=aid)
    if decision.get("routing_mode") == "public_pool":
        record_public_pool_premium(task_id, estimate_credits * 0.1, account_id=aid)
    return result


def get_task_key(task_id: str) -> str | None:
    with get_pool_store()._conn() as conn:
        row = conn.execute("SELECT key_id FROM task_key_binding WHERE task_id=?", (task_id,)).fetchone()
    return str(row["key_id"]) if row else None


def get_task_routing(task_id: str) -> dict[str, Any] | None:
    return get_pool_store().get_routing_decision(task_id)


def record_key_event(
    key_id: str,
    failure_kind: FailureKind,
    *,
    task_id: str | None = None,
    contributor_id: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """記錄 Key 事件；僅 key_failure 觸發分期沒收，balance_exhausted 不追究貢獻者。"""
    store = get_pool_store()
    health = store.record_key_health_event(
        key_id,
        event=failure_kind,
        contributor_id=contributor_id,
        reason=reason,
    )
    from backend.billing.shared_pool import evaluate_key_health

    evaluated = evaluate_key_health(key_id, force_offline=(failure_kind == "key_failure"))
    forfeitures: list[dict[str, Any]] = []
    if failure_kind == "key_failure":
        forfeitures = store.forfeit_installments_for_key_failure(key_id, task_id=task_id)
    return {"health": health, "evaluated": evaluated, "forfeitures": forfeitures, "failure_kind": failure_kind}


def mark_failover(
    task_id: str,
    new_key_id: str,
    *,
    failure_kind: FailureKind = "key_failure",
    old_key_id: str | None = None,
    estimate_credits: float = 0,
    invalidate_cache: bool = True,
) -> dict[str, Any]:
    store = get_pool_store()
    failed_key = old_key_id or get_task_key(task_id)
    account_id, _ = _resolve_account_for_task(task_id)

    if failed_key and invalidate_cache and failure_kind == "key_failure":
        record_cache_invalidation(
            task_id=task_id,
            old_key_id=failed_key,
            new_key_id=new_key_id,
            cost_credits=max(estimate_credits, 1.0),
            account_id=account_id,
        )

    if account_id and estimate_credits > 0:
        decision = route_key_selection(
            task_id=task_id,
            account_id=account_id,
            model="default",
            estimate_credits=estimate_credits,
        )
        if not decision.get("rejected") and decision.get("primary_key_id"):
            new_key_id = str(decision["primary_key_id"])
        apply_routing_binding(task_id, decision)
    else:
        store.bind_task_key(task_id, new_key_id, reason=f"failover_{failure_kind}")

    result: dict[str, Any] = {"task_id": task_id, "new_key_id": new_key_id, "failure_kind": failure_kind}
    if failed_key and failure_kind == "key_failure":
        result["key_event"] = record_key_event(
            failed_key,
            "key_failure",
            task_id=task_id,
            reason="failover_abnormal",
        )
    elif failed_key:
        result["key_event"] = record_key_event(
            failed_key,
            "balance_exhausted",
            task_id=task_id,
            reason="consumer_balance_exhausted",
        )
    return result
