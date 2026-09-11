"""靈境積分商業計費：方案、計量、配額、功能包閘門。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.billing.context import billing_user_id
from backend.billing.credits import credits_for_llm_tokens, credits_for_raho_layer
from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
from backend.billing.metering import meter_llm, meter_raho_layer, meter_quant_call, require_feature
from backend.billing.plans import PACK_QUANT, plan_has_feature
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import POOL_MONTHLY_GRANT, POOL_PURCHASED
from backend.billing.pools_service import PoolsService, TransferForbiddenError, get_pools_service
from backend.billing.pricing_engine import compute_cost_credits
from backend.billing.quota import BillingService, reset_billing_service
from backend.billing.store import BillingStore, reset_billing_store
from backend.billing.task_lifecycle import begin_billed_task, complete_billed_task, record_llm_usage


@pytest.fixture()
def billing_store(tmp_path, monkeypatch):
    db = str(tmp_path / "billing_test.sqlite3")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", db)
    store = BillingStore(db_path=db)
    reset_billing_store(store)
    reset_billing_service(BillingService(store))
    yield store
    reset_billing_store(None)
    reset_billing_service(None)


def test_free_plan_seed_credits(billing_store):
    svc = BillingService(billing_store)
    acct = svc.ensure_account("alice", "free")
    assert acct["plan_id"] == "free"
    assert acct["balance_credits"] == 10000
    assert acct["monthly_quota_credits"] == 10000


def test_debit_and_ledger(billing_store):
    svc = BillingService(billing_store)
    svc.ensure_account("bob", "free")
    svc.debit_credits("bob", 100, source="llm_tokens", reference="test")
    acct = svc.get_account("bob")
    assert acct["balance_credits"] == 9900
    assert svc.ledger("bob")[0]["source"] == "llm_tokens"


def test_insufficient_credits(billing_store):
    svc = BillingService(billing_store)
    svc.ensure_account("carol", "free")
    svc.debit_credits("carol", 9999, source="test")
    with pytest.raises(InsufficientCreditsError):
        svc.debit_credits("carol", 5, source="test")


def test_plan_upgrade(billing_store):
    svc = BillingService(billing_store)
    svc.ensure_account("dave", "free")
    acct = svc.set_plan("dave", "pro")
    assert acct["plan_id"] == "pro"
    assert plan_has_feature("pro", PACK_QUANT)


def test_quant_pack_gating_free_user(billing_store):
    svc = BillingService(billing_store)
    svc.ensure_account("erin", "free")
    token = billing_user_id.set("erin")
    try:
        with pytest.raises(FeatureNotEntitledError):
            require_feature(PACK_QUANT)
    finally:
        billing_user_id.reset(token)


def test_quant_allowed_on_pro(billing_store):
    svc = BillingService(billing_store)
    svc.set_plan("frank", "pro")
    token = billing_user_id.set("frank")
    try:
        before = svc.get_account("frank")["balance_credits"]
        meter_quant_call(reference="test")
        after = svc.get_account("frank")["balance_credits"]
        assert after < before
    finally:
        billing_user_id.reset(token)


def test_llm_token_metering(billing_store):
    svc = BillingService(billing_store)
    svc.set_plan("grace", "pro")
    token = billing_user_id.set("grace")
    try:
        before = svc.get_account("grace")["balance_credits"]
        meter_llm("gpt-4o-mini", 1000, 500, reference="unit")
        after = svc.get_account("grace")["balance_credits"]
        expected = credits_for_llm_tokens("gpt-4o-mini", 1000, 500)
        assert before - after == pytest.approx(expected, rel=1e-3)
        assert len(svc.usage_events("grace")) >= 1
    finally:
        billing_user_id.reset(token)


def test_raho_layer_metering(billing_store):
    svc = BillingService(billing_store)
    svc.set_plan("helen", "team")
    token = billing_user_id.set("helen")
    try:
        before = svc.get_account("helen")["balance_credits"]
        meter_raho_layer("L3", reference="item-1")
        after = svc.get_account("helen")["balance_credits"]
        assert before - after == credits_for_raho_layer("L3")
    finally:
        billing_user_id.reset(token)


def test_reserve_and_settle(billing_store):
    svc = BillingService(billing_store)
    svc.ensure_account("ivan", "pro")
    rid = svc.reserve("ivan", 10)
    svc.settle(rid, "ivan", 8, source="task", reference="t1")
    assert svc.get_account("ivan")["balance_credits"] == 100000 - 8


def test_docker_settle_tick_debits_credits(billing_store, monkeypatch):
    from backend.billing.docker_meter import DockerBillingTracker, reset_docker_billing_tracker

    tracker = DockerBillingTracker()
    reset_docker_billing_tracker(tracker)
    svc = BillingService(billing_store)
    svc.ensure_account("dockuser", "pro")
    tracker.assign_owner("frontend", "dockuser")

    class FakeDM:
        available = True

        def list_containers(self):
            return [
                {
                    "service": "frontend",
                    "name": "evoloop-frontend-1",
                    "status": "Up 2 minutes",
                    "uptime_seconds": 120.0,
                }
            ]

    monkeypatch.setattr("backend.services.docker_manager.get_docker_manager", lambda: FakeDM())

    token = billing_user_id.set("dockuser")
    try:
        before = svc.get_account("dockuser")["balance_credits"]
        charges = tracker.settle_tick("dockuser")
        assert len(charges) == 1
        assert charges[0]["service"] == "frontend"
        after = svc.get_account("dockuser")["balance_credits"]
        assert after < before
        events = svc.usage_events("dockuser", limit=5)
        assert any(e["event_type"] == "docker_runtime" for e in events)
        ledger = svc.ledger("dockuser", limit=5)
        assert any(row["source"] == "docker" for row in ledger)
    finally:
        billing_user_id.reset(token)
        reset_docker_billing_tracker(None)


def test_docker_start_preflight_insufficient(billing_store):
    from backend.billing.docker_api import preflight_docker_start
    from backend.billing.docker_meter import DockerBillingTracker, reset_docker_billing_tracker

    tracker = DockerBillingTracker()
    reset_docker_billing_tracker(tracker)
    svc = BillingService(billing_store)
    svc.ensure_account("broke", "free")
    svc.debit_credits("broke", 9999.9, source="test")
    token = billing_user_id.set("broke")
    try:
        with pytest.raises(InsufficientCreditsError):
            preflight_docker_start("frontend")
    finally:
        billing_user_id.reset(token)
        reset_docker_billing_tracker(None)


def test_spend_priority_monthly_before_purchased(billing_store):
    pools = get_pool_store()
    uid = "pool_user"
    billing_store.ensure_account(uid, "free")
    pools.credit_pool(uid, POOL_PURCHASED, 1000, source="test", description="purchased")
    pools.spend_from_pools(uid, 500, source="test")
    bals = pools.get_balances(uid)
    assert bals.get(POOL_MONTHLY_GRANT, 0) == 9500
    assert bals.get(POOL_PURCHASED, 0) == 1000


def test_monthly_rollover_proportional(billing_store):
    pools = get_pool_store()
    uid = "rollover_user"
    billing_store.ensure_account(uid, "free")
    pools.spend_from_pools(uid, 8000, source="test")
    results = pools.run_monthly_rollover("2025-08")
    row = next(r for r in results if r["account_id"] == uid)
    assert row["unused"] == 2000
    assert row["rolled"] == 1000
    assert row["forfeited"] == 1000
    bals = pools.get_balances(uid)
    assert bals.get(POOL_MONTHLY_GRANT, 0) == 0
    assert bals.get(POOL_PURCHASED, 0) == 1000


def test_reserve_settle_and_refund(billing_store):
    token = billing_user_id.set("reserve_user")
    try:
        billing_store.ensure_account("reserve_user", "pro")
        begun = begin_billed_task("reserve_user", baseline_tokens=100, iterations=1, roles=1, model="gpt-4o-mini")
        tid = begun["task_id"]
        record_llm_usage(tid, input_tokens=100, output_tokens=50, model="gpt-4o-mini")
        done = complete_billed_task(tid)
        assert done["reserved"] >= done["actual"]
        assert done["refund"] >= 0
    finally:
        billing_user_id.reset(token)


def test_pricing_snapshot_immutable(billing_store):
    pools = get_pool_store()
    uid = "snap_user"
    billing_store.ensure_account(uid, "pro")
    begun = begin_billed_task(uid, baseline_tokens=200, model="gpt-4o-mini")
    snap_v1 = pools.get_task_snapshot(begun["task_id"])["pricing_config_version"]
    with pools._conn() as conn:
        conn.execute(
            "INSERT INTO pricing_configs(status, effective_at, config_json, created_by, reason, created_at) VALUES ('active', datetime('now'), '{}', 'test', 'v2', datetime('now'))"
        )
    snap_v2_active = pools.active_pricing_config()["version"]
    snap_task = pools.get_task_snapshot(begun["task_id"])["pricing_config_version"]
    assert snap_task == snap_v1
    assert snap_v2_active >= snap_v1


def test_transfer_forbidden(billing_store):
    svc = PoolsService()
    with pytest.raises(TransferForbiddenError):
        svc.transfer("a", "b", 10)


def test_pricing_engine_cache_tokens(billing_store):
    pools = get_pool_store()
    cfg = pools.active_pricing_config()["config"]
    full = compute_cost_credits(cfg, model="gpt-4o-mini", input_tokens=1000, output_tokens=0)
    cached = compute_cost_credits(cfg, model="gpt-4o-mini", input_tokens=1000, output_tokens=0, cached_tokens=1000)
    assert cached < full


def test_billing_api(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "bill_user")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "bill_secret")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "bill_user", "password": "bill_secret"})
        token = login.json()["token"]
        headers = {"X-Linkin-Gate": token}
        resp = client.get("/billing", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["account"]["balance_credits"] > 0
        assert len(body["plans"]) >= 4
        topup = client.post("/billing/topup", headers=headers, json={"credits": 500})
        assert topup.status_code == 200
