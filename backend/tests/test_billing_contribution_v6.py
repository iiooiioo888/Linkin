"""v6.0 貢獻積分：分期、提前解鎖、Key 故障、動態閾值、半衰期、新表。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.billing.appeals import create_appeal, resolve_appeal
from backend.billing.contribution_service import (
    contribution_status,
    early_unlock_contribution,
    lock_contribution,
    process_due_installments,
    run_contribution_decay,
)
from backend.billing.contribution_threshold import compute_lock_threshold
from backend.billing.key_binding import mark_failover, record_key_event
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import (
    CONTRIBUTION_UNLOCKED_CONVERT_RATIO,
    CONTRIBUTION_UNLOCKED_DECAY,
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_PURCHASED,
)
from backend.billing.pools_service import PoolsService
from backend.billing.quota import BillingService, reset_billing_service
from backend.billing.store import BillingStore, reset_billing_store


@pytest.fixture()
def billing_store(tmp_path, monkeypatch):
    db = str(tmp_path / "billing_v6.sqlite3")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", db)
    store = BillingStore(db_path=db)
    reset_billing_store(store)
    reset_billing_service(BillingService(store))
    yield store
    reset_billing_store(None)
    reset_billing_service(None)


def _seed_unlocked(uid: str, amount: float) -> None:
    get_pool_store().credit_pool(uid, POOL_CONTRIBUTION_UNLOCKED, amount, source="reward", origin="test")


def _force_due(installment_id: str) -> None:
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    with get_pool_store()._conn() as conn:
        conn.execute("UPDATE lock_installments SET next_due_at=? WHERE installment_id=?", (past, installment_id))


def test_v6_tables_exist(billing_store):
    pools = get_pool_store()
    with pools._conn() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for name in ("users", "key_health", "subtasks", "cache_prefixes", "key_cache_profile", "contribution_decay_log"):
        assert name in tables


def test_dynamic_lock_threshold_not_fixed_50(billing_store):
    billing_store.ensure_account("thr_user", "pro")
    thr_low = compute_lock_threshold(unlocked=10, locked=0, plan_id="pro")
    thr_high = compute_lock_threshold(unlocked=500, locked=200, plan_id="free")
    assert thr_low != 50.0 or thr_high != 50.0
    assert thr_low >= 30.0
    assert thr_high <= 200.0


def test_lock_installment_schedule_and_payout(billing_store):
    uid = "inst_user"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 200)
    locked = lock_contribution(uid, 90, 90)
    iid = locked["installment_id"]
    inst = get_pool_store().get_lock_installment(iid)
    assert inst is not None
    assert inst["interval_days"] == 30
    assert inst["paid_installments"] == 0
    _force_due(iid)
    processed = process_due_installments(uid)
    assert len(processed) == 1
    assert processed[0]["principal_paid"] == pytest.approx(30.0, rel=1e-3)
    assert processed[0]["reward_paid"] == pytest.approx(90 * 0.08 / 3, rel=1e-3)
    bals = get_pool_store().get_balances(uid)
    assert bals.get(POOL_PURCHASED, 0) > 0


def test_installment_not_processed_before_due(billing_store):
    uid = "due_wait"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 200)
    locked = lock_contribution(uid, 60, 30)
    iid = locked["installment_id"]
    processed = process_due_installments(uid, force=False)
    assert processed == []
    inst = get_pool_store().get_lock_installment(iid)
    assert inst is not None
    assert inst["paid_installments"] == 0


def test_early_unlock_penalty_to_fault_pool(billing_store):
    uid = "early_user"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 200)
    locked = lock_contribution(uid, 100, 90)
    iid = locked["installment_id"]
    result = early_unlock_contribution(uid, iid)
    assert result["penalty_principal"] == pytest.approx(5.0, rel=1e-3)
    assert result["forfeited_amount"] > result["penalty_principal"]
    with get_pool_store()._conn() as conn:
        fp = conn.execute("SELECT COALESCE(SUM(amount),0) AS t FROM fault_pool WHERE installment_id=?", (iid,)).fetchone()
    assert float(fp["t"]) > 0
    inst = get_pool_store().get_lock_installment(iid)
    assert inst is not None
    assert inst["status"] == "early_unlocked"


def test_key_failure_forfeit_vs_balance_exhausted(billing_store):
    uid = "key_fail_user"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 200)
    pools = get_pool_store()
    bind = pools.bind_contributor_key(uid, "sk-test-key-abcdefgh")
    key_id = bind["key_id"]
    locked = lock_contribution(uid, 90, 30)
    iid = locked["installment_id"]
    with pools._conn() as conn:
        conn.execute("UPDATE lock_installments SET key_id=? WHERE installment_id=?", (key_id, iid))

    balance_evt = record_key_event(key_id, "balance_exhausted", reason="consumer_out_of_credits")
    assert balance_evt["forfeitures"] == []
    inst_before = pools.get_lock_installment(iid)
    assert inst_before is not None
    assert inst_before["status"] == "active"

    fail_evt = record_key_event(key_id, "key_failure", task_id="task-1", reason="provider_401")
    assert len(fail_evt["forfeitures"]) == 1
    inst_after = pools.get_lock_installment(iid)
    assert inst_after is not None
    assert inst_after["status"] == "forfeited_key_failure"
    assert inst_after.get("appeal_deadline")


def test_key_failure_appeal_and_restore(billing_store):
    uid = "appeal_key_user"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 200)
    pools = get_pool_store()
    bind = pools.bind_contributor_key(uid, "sk-test-key-appeal01")
    key_id = bind["key_id"]
    locked = lock_contribution(uid, 60, 30)
    iid = locked["installment_id"]
    with pools._conn() as conn:
        conn.execute("UPDATE lock_installments SET key_id=? WHERE installment_id=?", (key_id, iid))
    record_key_event(key_id, "key_failure", task_id="t-appeal")
    inst = pools.get_lock_installment(iid)
    forfeited = float(inst["forfeited_amount"])
    created = create_appeal(
        uid,
        reason="認為非我方故障",
        detail="供應商維護",
        appeal_kind="key_failure_forfeiture",
        installment_id=iid,
    )
    assert created["appeal_kind"] == "key_failure_forfeiture"
    resolved = resolve_appeal(created["appeal_id"], status="approved", restore_credits=True)
    assert resolved["restored_credits"] == pytest.approx(forfeited, rel=1e-3)


def test_contribution_decay_half_life(billing_store):
    uid = "decay_user"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 100)
    past = (datetime.now(timezone.utc) - timedelta(days=100)).replace(microsecond=0).isoformat()
    with get_pool_store()._conn() as conn:
        conn.execute(
            "INSERT INTO contribution_decay_log(account_id, last_decay_at) VALUES (?, ?)",
            (uid, past),
        )
    results = run_contribution_decay()
    row = next(r for r in results if r["account_id"] == uid)
    assert row["decayed"] == pytest.approx(100 * (1 - CONTRIBUTION_UNLOCKED_DECAY), rel=1e-3)
    assert row["after"] == pytest.approx(100 * CONTRIBUTION_UNLOCKED_DECAY, rel=1e-3)


def test_convert_ratio_unchanged(billing_store):
    pools = PoolsService()
    uid = "convert_v6"
    billing_store.ensure_account(uid, "free")
    _seed_unlocked(uid, 50)
    result = pools.convert_contribution_unlocked(uid, 50)
    assert result["purchased_credits"] == pytest.approx(50 * CONTRIBUTION_UNLOCKED_CONVERT_RATIO)


def test_contribution_status_dynamic_notice(billing_store):
    uid = "status_user"
    billing_store.ensure_account(uid, "enterprise")
    _seed_unlocked(uid, 80)
    status = contribution_status(uid)
    assert status["threshold_dynamic"] is True
    assert "動態閾值" in status["notice_zh"]


def test_scaffolding_read_write_new_tables(billing_store):
    pools = get_pool_store()
    pools.ensure_user_profile("scaffold_user", email="u@test.local")
    pools.record_key_health_event("key_scaffold", event="balance_exhausted")
    pools.upsert_subtask(subtask_id="st_1", task_id="task_1", account_id="scaffold_user", estimate_credits=10)
    pools.record_cache_prefix_hit(key_id="key_scaffold", prefix_hash="abc123", savings_credits=0.5)
    with pools._conn() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE user_id='scaffold_user'").fetchone()
        assert conn.execute("SELECT 1 FROM key_health WHERE key_id='key_scaffold'").fetchone()
        assert conn.execute("SELECT 1 FROM subtasks WHERE subtask_id='st_1'").fetchone()
        assert conn.execute("SELECT 1 FROM cache_prefixes WHERE prefix_hash='abc123'").fetchone()
        assert conn.execute("SELECT 1 FROM key_cache_profile WHERE key_id='key_scaffold'").fetchone()


def test_mark_failover_distinguishes_failure_kind(billing_store):
    pools = get_pool_store()
    pools.bind_task_key("task_fail", "old_key")
    out_key = mark_failover("task_fail", "new_key", failure_kind="key_failure", old_key_id="old_key")
    assert out_key["failure_kind"] == "key_failure"
    assert "key_event" in out_key

    pools.bind_task_key("task_bal", "old_key2")
    out_bal = mark_failover("task_bal", "new_key2", failure_kind="balance_exhausted", old_key_id="old_key2")
    assert out_bal["failure_kind"] == "balance_exhausted"


def test_contributor_api_early_unlock(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "api_early")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "api_early_secret")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    _seed_unlocked("api_early", 200)
    billing_store.ensure_account("api_early", "free")
    lock_contribution("api_early", 50, 30)

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "api_early", "password": "api_early_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"]}
        status = client.get("/billing/contributor/contribution/status", headers=headers)
        iid = status.json()["installments"][0]["installment_id"]
        resp = client.post(
            "/billing/contributor/contribution/early-unlock",
            headers=headers,
            json={"installment_id": iid},
        )
        assert resp.status_code == 200
        assert resp.json()["forfeited_amount"] > 0
