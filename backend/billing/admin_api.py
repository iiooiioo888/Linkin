"""定價中心與積分政策 Admin API。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.billing.fault_pool import fault_pool_status
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import POOL_CONTRIBUTION_UNLOCKED
from backend.billing.appeals import list_appeals, resolve_appeal
from backend.billing.pricing_engine import DEFAULT_CREDIT_POLICY, DEFAULT_PRICING_CONFIG
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS

router = APIRouter(prefix="/admin/billing", tags=["admin-billing"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PricingConfigBody(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    effective_at: str | None = None
    reason: str = ""


class CreditPolicyBody(BaseModel):
    monthly_rollover_ratio: float = 0.5
    rollover_cap: float = 50000
    by_tier: dict[str, Any] = Field(default_factory=dict)
    effective_at: str | None = None
    reason: str = ""


class ContributionSeedBody(BaseModel):
    account_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    note: str = ""


@router.post("/contribution/seed")
def admin_seed_contribution(body: ContributionSeedBody, operator: str = "admin") -> dict[str, Any]:
    """Admin / dev：注入 contribution_unlocked 供 lock/convert 測試。"""
    store = get_pool_store()
    store.ensure_pools(body.account_id.strip())
    store.credit_pool(
        body.account_id.strip(),
        POOL_CONTRIBUTION_UNLOCKED,
        body.amount,
        source="admin_seed",
        description=body.note or f"Admin 種子 by {operator}",
        origin="admin_dev_seed",
    )
    bals = store.get_balances(body.account_id.strip())
    return {
        "account_id": body.account_id.strip(),
        "amount": body.amount,
        "contribution_unlocked": float(bals.get(POOL_CONTRIBUTION_UNLOCKED, 0)),
        "operator": operator,
    }


@router.get("/pricing-configs")
def list_pricing_configs() -> dict[str, Any]:
    with get_pool_store()._conn() as conn:
        rows = conn.execute(
            "SELECT version, status, effective_at, created_by, reason, created_at FROM pricing_configs ORDER BY version DESC LIMIT 50"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/pricing-configs/active")
def get_active_pricing() -> dict[str, Any]:
    return get_pool_store().active_pricing_config()


@router.post("/pricing-configs")
def create_pricing_config(body: PricingConfigBody, operator: str = "admin") -> dict[str, Any]:
    store = get_pool_store()
    cfg = body.config or DEFAULT_PRICING_CONFIG
    now = _utc_now()
    eff = body.effective_at or now
    with store._conn() as conn:
        cur = conn.execute(
            """INSERT INTO pricing_configs(status, effective_at, config_json, created_by, reason, created_at)
               VALUES ('draft', ?, ?, ?, ?, ?)""",
            (eff, json.dumps(cfg, ensure_ascii=False), operator, body.reason, now),
        )
        version = int(cur.lastrowid)
        conn.execute(
            """INSERT INTO pricing_config_audit(entity_type, version, operator, action, new_json, reason, created_at)
               VALUES ('pricing_configs', ?, ?, 'create', ?, ?, ?)""",
            (version, operator, json.dumps(cfg, ensure_ascii=False), body.reason, now),
        )
    return {"version": version, "status": "draft"}


@router.post("/pricing-configs/{version}/activate")
def activate_pricing_config(version: int, operator: str = "admin", reason: str = "") -> dict[str, Any]:
    store = get_pool_store()
    now = _utc_now()
    with store._conn() as conn:
        row = conn.execute("SELECT config_json FROM pricing_configs WHERE version=?", (version,)).fetchone()
        if not row:
            raise HTTPException(404, "定價版本不存在")
        conn.execute("UPDATE pricing_configs SET status='archived' WHERE status='active'")
        conn.execute("UPDATE pricing_configs SET status='active' WHERE version=?", (version,))
        conn.execute(
            """INSERT INTO pricing_config_audit(entity_type, version, operator, action, reason, created_at)
               VALUES ('pricing_configs', ?, ?, 'activate', ?, ?)""",
            (version, operator, reason, now),
        )
    return {"version": version, "status": "active"}


@router.post("/pricing-configs/{version}/rollback")
def rollback_pricing_config(version: int, operator: str = "admin", reason: str = "") -> dict[str, Any]:
    return activate_pricing_config(version, operator=operator, reason=reason or "rollback")


@router.get("/credit-policies")
def list_credit_policies() -> dict[str, Any]:
    with get_pool_store()._conn() as conn:
        rows = conn.execute(
            """SELECT version, status, monthly_rollover_ratio, rollover_cap, effective_at, created_at
               FROM credit_policies ORDER BY version DESC LIMIT 50"""
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/credit-policies")
def create_credit_policy(body: CreditPolicyBody, operator: str = "admin") -> dict[str, Any]:
    store = get_pool_store()
    now = _utc_now()
    eff = body.effective_at or now
    with store._conn() as conn:
        cur = conn.execute(
            """INSERT INTO credit_policies(status, effective_at, monthly_rollover_ratio, rollover_cap,
               by_tier_json, created_by, reason, created_at)
               VALUES ('draft', ?, ?, ?, ?, ?, ?, ?)""",
            (
                eff,
                body.monthly_rollover_ratio,
                body.rollover_cap,
                json.dumps(body.by_tier, ensure_ascii=False),
                operator,
                body.reason,
                now,
            ),
        )
        version = int(cur.lastrowid)
    return {"version": version, "status": "draft"}


@router.post("/credit-policies/{version}/activate")
def activate_credit_policy(version: int, operator: str = "admin") -> dict[str, Any]:
    with get_pool_store()._conn() as conn:
        if not conn.execute("SELECT 1 FROM credit_policies WHERE version=?", (version,)).fetchone():
            raise HTTPException(404, "積分政策版本不存在")
        conn.execute("UPDATE credit_policies SET status='archived' WHERE status='active'")
        conn.execute("UPDATE credit_policies SET status='active' WHERE version=?", (version,))
    return {"version": version, "status": "active"}


@router.get("/rollover-records")
def list_rollover_records(limit: int = 50) -> dict[str, Any]:
    with get_pool_store()._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM rollover_records ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("/rollover/run")
def trigger_rollover(month_key: str | None = None) -> dict[str, Any]:
    results = get_pool_store().run_monthly_rollover(month_key)
    return {"processed": len(results), "results": results}


@router.get("/vendor-configs")
def list_vendor_configs() -> dict[str, Any]:
    with get_pool_store()._conn() as conn:
        rows = conn.execute(
            "SELECT version, status, effective_at, created_at FROM vendor_configs ORDER BY version DESC LIMIT 50"
        ).fetchall()
    return {"items": [dict(r) for r in rows], "active": get_pool_store().active_vendor_config()}


@router.post("/vendor-configs")
def create_vendor_config(config: dict[str, Any], operator: str = "admin", reason: str = "") -> dict[str, Any]:
    now = _utc_now()
    body = config or DEFAULT_VENDOR_CONFIGS
    with get_pool_store()._conn() as conn:
        cur = conn.execute(
            """INSERT INTO vendor_configs(status, effective_at, config_json, created_by, reason, created_at)
               VALUES ('draft', ?, ?, ?, ?, ?)""",
            (now, json.dumps(body, ensure_ascii=False), operator, reason, now),
        )
        version = int(cur.lastrowid)
    return {"version": version, "status": "draft"}


@router.post("/vendor-configs/{version}/activate")
def activate_vendor_config(version: int) -> dict[str, Any]:
    with get_pool_store()._conn() as conn:
        if not conn.execute("SELECT 1 FROM vendor_configs WHERE version=?", (version,)).fetchone():
            raise HTTPException(404, "廠商配置版本不存在")
        conn.execute("UPDATE vendor_configs SET status='archived' WHERE status='active'")
        conn.execute("UPDATE vendor_configs SET status='active' WHERE version=?", (version,))
    return {"version": version, "status": "active"}


@router.get("/appeals")
def admin_list_appeals(limit: int = 50) -> dict[str, Any]:
    return {"items": list_appeals(None, limit=limit)}


@router.post("/appeals/{appeal_id}/resolve")
def admin_resolve_appeal(appeal_id: str, note: str = "", restore_credits: bool = False) -> dict[str, Any]:
    try:
        return resolve_appeal(appeal_id, note=note, restore_credits=restore_credits)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/cache-stats")
def cache_stats(account_id: str | None = None) -> dict[str, Any]:
    return get_pool_store().cache_stats_summary(account_id)


@router.get("/fault-pool")
def fault_pool_stats() -> dict[str, Any]:
    status = fault_pool_status()
    with get_pool_store()._conn() as conn:
        legacy = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS entries FROM fault_pool").fetchone()
        recent = conn.execute("SELECT * FROM fault_pool ORDER BY created_at DESC LIMIT 20").fetchall()
    return {
        **status,
        "legacy_total": float(legacy["total"]),
        "legacy_entries": int(legacy["entries"]),
        "recent_inflows": [dict(r) for r in recent],
    }


@router.get("/routing/stats")
def routing_stats(limit: int = 30) -> dict[str, Any]:
    store = get_pool_store()
    with store._conn() as conn:
        rows = conn.execute(
            """SELECT routing_mode, COUNT(*) AS c FROM routing_decisions
               GROUP BY routing_mode ORDER BY c DESC"""
        ).fetchall()
        recent = conn.execute(
            "SELECT decision_id, task_id, account_id, routing_mode, created_at FROM routing_decisions ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return {
        "by_mode": [dict(r) for r in rows],
        "recent": [dict(r) for r in recent],
        "public_pool_paused": store.get_routing_runtime("public_pool_paused", False),
        "platform_take_rate": store.get_routing_runtime("platform_take_rate", 0.08),
    }


@router.get("/routing/task/{task_id}")
def routing_for_task(task_id: str) -> dict[str, Any]:
    decision = get_pool_store().get_routing_decision(task_id)
    if not decision:
        raise HTTPException(404, "尚無路由決策紀錄")
    return decision


@router.post("/fault-pool/resume-public")
def resume_public_pool(operator: str = "admin") -> dict[str, Any]:
    store = get_pool_store()
    store.set_routing_runtime("public_pool_paused", False)
    return {"public_pool_paused": False, "operator": operator}


@router.get("/task-ledger/{task_id}")
def task_ledger(task_id: str) -> dict[str, Any]:
    store = get_pool_store()
    with store._conn() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        ledger = conn.execute(
            "SELECT * FROM pool_ledger WHERE task_id=? ORDER BY created_at", (task_id,)
        ).fetchall()
        usage = conn.execute(
            "SELECT * FROM pool_usage_events WHERE task_id=? ORDER BY created_at", (task_id,)
        ).fetchall()
        binding = conn.execute("SELECT * FROM task_key_binding WHERE task_id=?", (task_id,)).fetchone()
    routing = store.get_routing_decision(task_id)
    return {
        "task": dict(task) if task else None,
        "ledger": [dict(r) for r in ledger],
        "usage_events": [dict(r) for r in usage],
        "key_binding": dict(binding) if binding else None,
        "routing": routing,
    }
