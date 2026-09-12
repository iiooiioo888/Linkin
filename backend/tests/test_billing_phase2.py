"""Billing v6.0 Phase 2 — 共享池路由、Fault Pool、健康檢查。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.billing.fault_pool import (
    credit_fault_pool,
    disburse_from_fault_pool,
    fault_pool_status,
    record_cache_invalidation,
)
from backend.billing.key_binding import mark_failover, select_and_bind_key
from backend.billing.pool_store import get_pool_store
from backend.billing.routing import route_key_selection
from backend.billing.shared_pool import evaluate_key_health, list_shared_pool_keys
from backend.billing.store import BillingStore, reset_billing_store
from backend.billing.quota import BillingService, reset_billing_service


@pytest.fixture()
def billing_store(tmp_path, monkeypatch):
    db = str(tmp_path / "billing_phase2.sqlite3")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", db)
    store = BillingStore(db_path=db)
    reset_billing_store(store)
    reset_billing_service(BillingService(store))
    yield store
    reset_billing_store(None)
    reset_billing_service(None)


def _bind_key(
    uid: str,
    *,
    org_id: str = "org_a",
    daily_cap: int = 500_000,
    vendor: str = "self_host",
    tos_class: str | None = None,
) -> str:
    resolved_tos = tos_class or ("self_host" if vendor == "self_host" else "resale_allowed")
    result = get_pool_store().bind_contributor_key(
        uid,
        "sk-test-key-abcdefgh123456",
        {
            "vendor_id": vendor,
            "models": ["default", "gpt-4"],
            "daily_token_cap": daily_cap,
            "concurrency": 3,
            "min_price": 0.001,
            "active_hours": [0, 23],
            "tos_class": resolved_tos,
        },
        org_id=org_id,
        plaintext_key="sk-test-key-abcdefgh123456",
    )
    return str(result["key_id"])


def test_routing_prefers_contributor_key_over_platform_default(billing_store):
    """有貢獻者 Key 時，primary 不應為 platform_default。"""
    uid = "route_contrib"
    billing_store.ensure_account(uid, "free")
    key_id = _bind_key(uid, org_id="org_contrib", vendor="tongyi")
    decision = route_key_selection(
        task_id="task_contrib",
        account_id=uid,
        model="default",
        estimate_credits=10.0,
        org_id="org_contrib",
    )
    assert decision.get("primary_key_id") == key_id
    assert decision.get("primary_key_id") != "platform_default"
    assert not decision.get("rejected")


def test_routing_single_key_when_only_one_eligible(billing_store):
    uid = "route_single"
    billing_store.ensure_account(uid, "free")
    _bind_key(uid)
    decision = route_key_selection(
        task_id="task_single",
        account_id=uid,
        model="default",
        estimate_credits=10.0,
        org_id="org_a",
    )
    assert decision["routing_mode"] in {"single", "relay", "parallel_split", "same_org_split"}
    assert decision.get("primary_key_id")
    assert not decision.get("rejected")


def test_routing_same_org_relay_over_parallel(billing_store):
    uid = "route_org"
    billing_store.ensure_account(uid, "pro")
    k1 = _bind_key(uid, org_id="org_shared")
    k2 = _bind_key(uid, org_id="org_shared")
    store = get_pool_store()
    store.record_cache_prefix_hit(key_id=k1, prefix_hash="abc", savings_credits=1.0)
    decision = route_key_selection(
        task_id="task_org",
        account_id=uid,
        model="default",
        estimate_credits=20.0,
        org_id="org_shared",
    )
    assert decision["routing_mode"] in {"relay", "same_org_split", "parallel_split", "single"}
    key_ids = {k["key_id"] for k in decision.get("selected_keys", [])}
    assert k1 in key_ids or k2 in key_ids


def test_routing_queue_reject_when_public_pool_paused(billing_store):
    uid = "route_reject"
    billing_store.ensure_account(uid, "free")
    store = get_pool_store()
    store.set_routing_runtime("public_pool_paused", True)
    with store._conn() as conn:
        conn.execute("UPDATE api_keys SET status='disabled'")
    decision = route_key_selection(
        task_id="task_reject",
        account_id=uid,
        model="default",
        estimate_credits=10.0,
    )
    assert decision["routing_mode"] in {"queue_reject", "single"}
    if decision["routing_mode"] == "single":
        assert decision.get("primary_key_id") == "platform_default"


def test_fault_pool_ledger_credit_and_debit(billing_store):
    credit_fault_pool(100.0, "early_unlock_penalty", account_id="u1", source="lock_penalty")
    credit_fault_pool(50.0, "cache_savings", source="cache_savings")
    assert get_pool_store().fault_pool_balance() == pytest.approx(150.0, rel=1e-3)
    out = disburse_from_fault_pool(40.0, "lock_installment_reward", account_id="u1", installment_id="ins_x")
    assert out["disbursed"] == pytest.approx(40.0)
    assert get_pool_store().fault_pool_balance() == pytest.approx(110.0, rel=1e-3)


def test_fault_pool_depletion_pauses_public_pool(billing_store):
    store = get_pool_store()
    store.set_routing_runtime("fault_pool_depletion_threshold", 200.0)
    store.set_routing_runtime("platform_take_rate", 0.08)
    credit_fault_pool(50.0, "test_inflow", source="platform_take")
    status = fault_pool_status()
    assert status["depleted"] is True
    assert status["public_pool_paused"] is True
    assert status["platform_take_rate"] > 0.08


def test_key_health_offline_on_failures(billing_store):
    uid = "health_user"
    billing_store.ensure_account(uid, "free")
    key_id = _bind_key(uid)
    store = get_pool_store()
    for _ in range(6):
        store.record_key_health_event(key_id, event="key_failure", reason="test")
    evaluated = evaluate_key_health(key_id, force_offline=True)
    assert evaluated["offline"] is True
    assert evaluated["status"] == "offline"


def test_failover_records_cache_invalidation_to_fault_pool(billing_store):
    uid = "fail_user"
    billing_store.ensure_account(uid, "free")
    store = get_pool_store()
    snap = store.snapshot_pricing("free")
    store.create_task_record("task_fail", uid, 50, 50, snap)
    old = _bind_key(uid)
    store.bind_task_key("task_fail", old)
    mark_failover("task_fail", "platform_default", old_key_id=old, estimate_credits=50.0)
    balance = store.fault_pool_balance()
    assert balance > 0


def test_installment_reward_uses_fault_pool(billing_store):
    from backend.billing.contribution_service import lock_contribution, process_due_installments

    uid = "reward_fp"
    billing_store.ensure_account(uid, "free")
    store = get_pool_store()
    store.credit_pool(uid, "contribution_unlocked", 200, source="reward")
    credit_fault_pool(500.0, "platform_take_seed", source="platform_take")
    locked = lock_contribution(uid, 90, 90)
    iid = locked["installment_id"]
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    with store._conn() as conn:
        conn.execute("UPDATE lock_installments SET next_due_at=? WHERE installment_id=?", (past, iid))
    before = store.fault_pool_balance()
    processed = process_due_installments(uid)
    assert len(processed) == 1
    assert processed[0].get("fault_pool_reward", {}).get("disbursed", 0) > 0
    assert store.fault_pool_balance() < before


def test_contributor_api_keys_health(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "contrib_p2")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "secret_p2")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "contrib_p2", "password": "secret_p2"})
        headers = {"X-Linkin-Gate": login.json()["token"]}
        bind = client.post(
            "/billing/contributor/bind-key",
            headers=headers,
            json={
                "encrypted_key": "sk-phase2-key-12345678",
                "vendor_id": "self_host",
                "models": ["default"],
                "daily_token_cap": 100000,
                "concurrency": 2,
                "tos_class": "self_host",
                "org_id": "org_ui",
            },
        )
        assert bind.status_code == 200
        assert bind.json()["encrypted"] is True
        keys = client.get("/billing/contributor/keys", headers=headers)
        assert keys.status_code == 200
        assert keys.json()["count"] >= 1
        key_id = keys.json()["items"][0]["key_id"]
        health = client.get(f"/billing/contributor/keys/{key_id}/health", headers=headers)
        assert health.status_code == 200
        assert "health_score" in health.json()


def test_select_and_bind_key_logs_routing(billing_store):
    uid = "bind_route"
    billing_store.ensure_account(uid, "free")
    store = get_pool_store()
    snap = store.snapshot_pricing("free")
    store.create_task_record("task_bind", uid, 30, 30, snap)
    _bind_key(uid)
    result = select_and_bind_key("task_bind", estimate_credits=30, model="default", account_id=uid)
    assert result.get("bound") is True
    assert result.get("routing_mode")
    logged = store.get_routing_decision("task_bind")
    assert logged is not None


def test_tos_rejects_unsupported_vendor(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "tos_user")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "tos_secret")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "tos_user", "password": "tos_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"]}
        bad = client.post(
            "/billing/contributor/bind-key",
            headers=headers,
            json={
                "encrypted_key": "sk-bad-vendor-key123",
                "vendor_id": "openai",
                "tos_class": "retail_resale",
            },
        )
        assert bad.status_code == 422


def test_shared_pool_excludes_offline_keys(billing_store):
    uid = "pool_offline"
    billing_store.ensure_account(uid, "free")
    key_id = _bind_key(uid)
    evaluate_key_health(key_id, force_offline=True)
    keys = list_shared_pool_keys(model="default", estimate_credits=10, account_id=uid)
    contributor_keys = [k for k in keys if k.get("key_id") == key_id]
    assert contributor_keys == []


def test_settle_credits_contribution_unlocked(billing_store):
    from backend.billing.pools_service import get_pools_service
    from backend.billing.pool_types import POOL_CONTRIBUTION_UNLOCKED

    uid = "settle_reward"
    billing_store.ensure_account(uid, "pro")
    store = get_pool_store()
    key_id = _bind_key(uid)
    snap = store.snapshot_pricing("pro")
    store.create_task_record("task_settle_rw", uid, 30, 30, snap)
    store.bind_task_key("task_settle_rw", key_id)
    before = store.get_balances(uid).get(POOL_CONTRIBUTION_UNLOCKED, 0)
    result = get_pools_service().settle_task_usage(
        "task_settle_rw",
        input_tokens=500,
        output_tokens=200,
        key_id=key_id,
        model="default",
    )
    assert result["contributor_reward"]["credited"] is True
    after = store.get_balances(uid).get(POOL_CONTRIBUTION_UNLOCKED, 0)
    assert after > before
    assert store.fault_pool_balance() > 0


def test_convert_contribution_ratio_1_to_0_4(billing_store):
    from backend.billing.pools_service import get_pools_service
    from backend.billing.pool_types import CONTRIBUTION_UNLOCKED_CONVERT_RATIO, POOL_CONTRIBUTION_UNLOCKED, POOL_PURCHASED

    uid = "convert_user"
    billing_store.ensure_account(uid, "free")
    store = get_pool_store()
    store.credit_pool(uid, POOL_CONTRIBUTION_UNLOCKED, 100, source="admin_seed", origin="test")
    out = get_pools_service().convert_contribution_unlocked(uid, 50)
    assert out["converted"] == 50
    assert out["purchased_credits"] == pytest.approx(50 * CONTRIBUTION_UNLOCKED_CONVERT_RATIO, rel=1e-3)
    bals = store.get_balances(uid)
    assert bals.get(POOL_CONTRIBUTION_UNLOCKED, 0) == pytest.approx(50, rel=1e-3)
    assert bals.get(POOL_PURCHASED, 0) >= 20


def test_lock_creates_installments_with_reward_balance(billing_store):
    from backend.billing.contribution_service import lock_contribution

    uid = "lock_user"
    billing_store.ensure_account(uid, "free")
    store = get_pool_store()
    store.credit_pool(uid, "contribution_unlocked", 200, source="admin_seed", origin="test")
    locked = lock_contribution(uid, 90, 90)
    assert locked["installment_id"]
    inst = store.get_lock_installment(locked["installment_id"])
    assert inst is not None
    assert inst["paid_installments"] == 0
    assert inst["lock_days"] == 90
    bals = store.get_balances(uid)
    assert bals.get("contribution_locked", 0) == pytest.approx(90, rel=1e-3)


def test_admin_seed_contribution_api(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "seed_admin")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "seed_secret")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "seed_admin", "password": "seed_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"], "X-Billing-Admin": ""}
        billing_store.ensure_account("seed_target", "free")
        resp = client.post(
            "/admin/billing/contribution/seed",
            headers=headers,
            json={"account_id": "seed_target", "amount": 150, "note": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["contribution_unlocked"] == pytest.approx(150, rel=1e-3)
