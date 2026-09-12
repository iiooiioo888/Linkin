"""靈境積分商業計費 v6.0：方案、多池、定價、申訴。"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from backend.billing.appeals import create_appeal, list_appeals
from backend.billing.context import (
    begin_chat_billing,
    billing_user_id,
    chat_billing_snapshot,
    end_chat_billing,
)
from backend.billing.credits import credits_for_raho_layer
from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
from backend.billing.metering import (
    meter_llm,
    meter_quant_call,
    meter_raho_layer,
    meter_reflection_iteration,
    require_feature,
)
from backend.billing.plans import PACK_QUANT, PLAN_DEFINITIONS, plan_has_feature
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import (
    CONTRIBUTION_UNLOCKED_CONVERT_RATIO,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_MONTHLY_GRANT,
    POOL_PURCHASED,
)
from backend.billing.pools_service import (
    PoolsService,
    ReserveRejectedError,
    TransferForbiddenError,
    evaluate_reserve_tier,
)
from backend.billing.pricing_engine import compute_cost_credits, compute_cost_with_meta
from backend.billing.quota import BillingService, reset_billing_service
from backend.billing.reward_engine import compute_reward, quality_score
from backend.billing.store import BillingStore, reset_billing_store
from backend.billing.task_lifecycle import begin_billed_task, complete_billed_task, record_llm_usage
from backend.billing.vendor_configs import detect_vendor


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


def test_team_plan_removed():
    from backend.billing.plans import get_plan, normalize_plan_id

    assert "team" not in PLAN_DEFINITIONS
    assert normalize_plan_id("team") == "business"
    plan = get_plan("team")
    assert plan["id"] == "business"


def test_plan_ladder_has_five_public_tiers():
    from backend.billing.plans import PLAN_ORDER, list_plans_public

    assert len(PLAN_ORDER) >= 5
    public = list_plans_public()
    assert len(public) >= 5
    ids = [p["id"] for p in public]
    assert ids == ["free", "starter", "pro", "business", "enterprise"]
    for p in public:
        assert "docker" in p
        assert "rate_multiplier" in p["docker"]
        assert "included_hours_per_month" in p["docker"]


def test_docker_rate_resolution_by_plan():
    from backend.billing.docker_pricing import get_effective_hourly_rate, get_plan_docker_terms
    from backend.company.docker_tools import get_service_hourly_rate

    base = get_service_hourly_rate("frontend")
    free_rate = get_effective_hourly_rate("frontend", "free")
    pro_rate = get_effective_hourly_rate("frontend", "pro")
    enterprise_rate = get_effective_hourly_rate("frontend", "enterprise")
    assert free_rate == round(base * 2.0, 6)
    assert pro_rate == round(base * 1.0, 6)
    assert enterprise_rate == round(base * 0.5, 6)
    assert get_plan_docker_terms("starter")["included_hours_per_month"] == 5


def test_docker_included_hours_reduce_charge():
    from backend.billing.docker_pricing import compute_docker_charge_usd

    charge = compute_docker_charge_usd("frontend", 2.0, "pro", included_used_hours=0)
    assert charge["free_hours"] == 2.0
    assert charge["billable_hours"] == 0.0
    assert charge["cost_usd"] == 0.0

    over = compute_docker_charge_usd("frontend", 5.0, "pro", included_used_hours=18)
    assert over["free_hours"] == 2.0
    assert over["billable_hours"] == 3.0
    assert over["cost_usd"] > 0


def test_legacy_team_account_migrates_to_business(billing_store):
    svc = BillingService(billing_store)
    billing_store.ensure_account("legacy_team", "team")
    acct = svc.get_account("legacy_team")
    assert acct["plan_id"] == "business"


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
        assert before > after
        assert len(svc.usage_events("grace")) >= 1
    finally:
        billing_user_id.reset(token)


def test_chat_billing_accumulator_with_session_task_id(billing_store):
    svc = BillingService(billing_store)
    svc.set_plan("chat_user", "pro")
    uid_token = billing_user_id.set("chat_user")
    bill_token = begin_chat_billing("sess-abc")
    try:
        meter_llm("qwen3.8-flash", 477, 454, task_id="sess-abc", reference="chat")
        snap = chat_billing_snapshot()
        assert snap is not None
        assert snap["credits_deducted"] > 0
        assert snap["input_tokens"] == 477
        assert snap["output_tokens"] == 454
        assert snap["call_count"] >= 1
        assert "qwen3.8-flash" in snap["models"]
        events = svc.usage_events("chat_user")
        assert events[-1]["task_id"] == "sess-abc"
    finally:
        end_chat_billing(bill_token)
        billing_user_id.reset(uid_token)


def test_chat_billing_includes_reflection_iteration(billing_store):
    svc = BillingService(billing_store)
    svc.ensure_account("reflect_user", "pro")
    uid_token = billing_user_id.set("reflect_user")
    bill_token = begin_chat_billing("sess-reflect")
    try:
        before = float(chat_billing_snapshot()["credits_deducted"])
        meter_reflection_iteration(1, task_id="sess-reflect", meta={"node": "improve_answer"})
        snap = chat_billing_snapshot()
        assert snap is not None
        assert snap["credits_deducted"] > before
    finally:
        end_chat_billing(bill_token)
        billing_user_id.reset(uid_token)


def test_low_balance_not_tied_to_enterprise_quota(billing_store):
    svc = BillingService(billing_store)
    svc.set_plan("enterprise_user", "enterprise")
    acct = svc.get_account("enterprise_user")
    assert acct["monthly_quota_credits"] >= 1_000_000
    assert acct["balance_credits"] > 1000
    assert acct["low_balance"] is False


def test_raho_layer_metering(billing_store):
    svc = BillingService(billing_store)
    svc.set_plan("helen", "enterprise")
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


def test_cost_formula_without_cache(billing_store):
    cfg = get_pool_store().active_pricing_config()["config"]
    cost = compute_cost_credits(cfg, model="gpt-4o-mini", input_tokens=1000, output_tokens=500)
    assert cost > 0


def test_cost_formula_with_cache_read(billing_store):
    cfg = get_pool_store().active_pricing_config()["config"]
    full = compute_cost_credits(cfg, model="gpt-4o-mini", input_tokens=1000, output_tokens=0)
    with_cache = compute_cost_credits(
        cfg, model="gpt-4o-mini", input_tokens=1000, output_tokens=0, cache_read_tokens=1000
    )
    assert with_cache < full


def test_cost_formula_cache_metadata_missing(billing_store):
    cfg = get_pool_store().active_pricing_config()["config"]
    meta = compute_cost_with_meta(
        cfg,
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=0,
        cache_metadata_missing=True,
    )
    assert meta["flags"].get("cache_metadata_missing") is True


def test_l3_cache_hit_savings(billing_store):
    cfg = get_pool_store().active_pricing_config()["config"]
    meta = compute_cost_with_meta(cfg, model="gpt-4o-mini", input_tokens=1000, output_tokens=500, l3_cache_hit=True)
    assert meta["flags"].get("l3_cache_hit") is True
    assert meta["cache_savings_credits"] > 0


def test_vendor_configs_detect(billing_store):
    assert detect_vendor("gpt-4o") == "openai"
    assert detect_vendor("gemini-pro") == "google"
    vc = get_pool_store().active_vendor_config()
    assert "openai" in vc["config"]


def test_reward_no_cache_in_quality(billing_store):
    q = quality_score(uptime=0.9, latency=0.9, stability=0.9, consumer_rating=0.8)
    assert 0 < q <= 1.0
    r = compute_reward(10.0, consumer_rating=0.8, lock_multiplier=1.08)
    assert r["contributor_reward"] > 0
    assert r["lock_multiplier"] == 1.08


def test_spend_priority_monthly_before_purchased(billing_store):
    pools = get_pool_store()
    uid = "pool_user"
    billing_store.ensure_account(uid, "free")
    pools.credit_pool(uid, POOL_PURCHASED, 1000, source="test", description="purchased", origin="purchase")
    pools.spend_from_pools(uid, 500, source="test")
    bals = pools.get_balances(uid)
    assert bals.get(POOL_MONTHLY_GRANT, 0) == 9500
    assert bals.get(POOL_PURCHASED, 0) == 1000


def test_monthly_rollover_proportional_and_idempotent(billing_store):
    pools = get_pool_store()
    uid = "rollover_user"
    billing_store.ensure_account(uid, "free")
    pools.spend_from_pools(uid, 8000, source="test")
    results = pools.run_monthly_rollover("2025-08")
    row = next(r for r in results if r["account_id"] == uid)
    assert row["unused"] == 2000
    # free 方案滾存比例 30%（見 DEFAULT_CREDIT_POLICY.by_tier.free）
    assert row["rolled"] == 600
    assert row["forfeited"] == 1400
    repeat = pools.run_monthly_rollover("2025-08")
    assert not any(r["account_id"] == uid for r in repeat)


def test_reserve_tiers(billing_store):
    assert evaluate_reserve_tier(40, 100) == "reject"
    assert evaluate_reserve_tier(60, 100) == "degrade"
    assert evaluate_reserve_tier(100, 100) == "normal"


def test_reserve_reject_below_half(billing_store):
    pools = PoolsService()
    billing_store.ensure_account("broke_reserve", "free")
    get_pool_store().spend_from_pools("broke_reserve", 9950, source="test")
    with pytest.raises(ReserveRejectedError):
        pools.reserve_for_task("broke_reserve", "task_reject", baseline_tokens=50000, model="gpt-4o")


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
    snap_task = pools.get_task_snapshot(begun["task_id"])["pricing_config_version"]
    assert snap_task == snap_v1


def test_lock_multiplier_snapshot(billing_store):
    billing_store.ensure_account("lock_user", "pro")
    begun = begin_billed_task("lock_user", baseline_tokens=100, model="gpt-4o-mini", lock_multiplier=1.08)
    snap = get_pool_store().get_task_snapshot(begun["task_id"])
    assert snap["lock_multiplier"] == 1.08
    assert begun["lock_multiplier"] == 1.08


def test_contribution_convert_ratio(billing_store):
    pools = PoolsService()
    uid = "contrib_user"
    billing_store.ensure_account(uid, "free")
    get_pool_store().credit_pool(
        uid, POOL_CONTRIBUTION_UNLOCKED, 100, source="reward", origin="contributor_reward"
    )
    result = pools.convert_contribution_unlocked(uid, 100)
    assert result["converted"] == 100
    assert result["purchased_credits"] == pytest.approx(100 * CONTRIBUTION_UNLOCKED_CONVERT_RATIO)
    bals = get_pool_store().get_balances(uid)
    assert bals.get(POOL_CONTRIBUTION_UNLOCKED, 0) == 0
    assert bals.get(POOL_PURCHASED, 0) == pytest.approx(100 * CONTRIBUTION_UNLOCKED_CONVERT_RATIO)


def test_transfer_forbidden(billing_store):
    svc = PoolsService()
    with pytest.raises(TransferForbiddenError):
        svc.transfer("a", "b", 10)


def test_billing_overview_api(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)
    monkeypatch.setenv("LINKIN_BILLING_ANONYMOUS_USER", "overview_user")
    from backend.main import app

    svc = BillingService(billing_store)
    svc.ensure_account("overview_user", "free")
    svc.debit_credits("overview_user", 120.5, source="test", reference="overview-spend")

    with TestClient(app) as client:
        resp = client.get("/billing/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "overview_user"
        assert data["monthly_used_credits"] == pytest.approx(120.5)
        assert data["balance_credits"] > 0
        assert data["unhealthy_keys_count"] == 0
        assert data["unhealthy_keys"] == []


def test_transfer_api_403(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "t_user")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "t_secret")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)
    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "t_user", "password": "t_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"]}
        resp = client.post("/billing/transfer", headers=headers)
        assert resp.status_code == 403


def test_atomic_debit_race(billing_store):
    pools = get_pool_store()
    uid = "race_user"
    billing_store.ensure_account(uid, "free")
    errors: list[Exception] = []

    def worker():
        try:
            pools.spend_from_pools(uid, 5000, source="race")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    bals = pools.get_balances(uid)
    total = bals.get(POOL_MONTHLY_GRANT, 0) + bals.get(POOL_PURCHASED, 0)
    assert total >= 0
    assert len(errors) >= 1


def test_appeals_basic(billing_store):
    billing_store.ensure_account("appeal_user", "free")
    created = create_appeal("appeal_user", task_id="t1", reason="計費異常", detail="多扣款")
    assert created["status"] == "pending"
    items = list_appeals("appeal_user")
    assert any(i["appeal_id"] == created["appeal_id"] for i in items)


def test_docker_settle_tick_debits_credits(billing_store, monkeypatch):
    from backend.billing.docker_meter import DockerBillingTracker, reset_docker_billing_tracker

    tracker = DockerBillingTracker()
    reset_docker_billing_tracker(tracker)
    svc = BillingService(billing_store)
    svc.ensure_account("dockuser", "pro")
    tracker.assign_owner("frontend", "dockuser")
    # 耗盡含額，確保產生實際扣款
    from backend.billing.docker_meter import _month_key

    tracker._included_used_hours["dockuser"] = 999.0
    tracker._included_period["dockuser"] = _month_key()

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
        after = svc.get_account("dockuser")["balance_credits"]
        assert after < before
        assert charges[0]["plan_id"] == "pro"
        assert charges[0]["billable_hours"] > 0
    finally:
        billing_user_id.reset(token)
        reset_docker_billing_tracker(None)


def test_docker_settle_uses_plan_rate_multiplier(billing_store, monkeypatch):
    from backend.billing.docker_meter import DockerBillingTracker, reset_docker_billing_tracker
    from backend.billing.docker_pricing import get_effective_hourly_rate

    tracker = DockerBillingTracker()
    reset_docker_billing_tracker(tracker)
    svc = BillingService(billing_store)
    svc.ensure_account("free_docker", "free")
    tracker.assign_owner("frontend", "free_docker")
    # 耗盡含額（free 無含額）並以 2h uptime 觸發全額計費
    tracker._included_used_hours["free_docker"] = 999.0
    tracker._included_period["free_docker"] = __import__("backend.billing.docker_meter", fromlist=["_month_key"])._month_key()

    class FakeDM:
        available = True

        def list_containers(self):
            return [
                {
                    "service": "frontend",
                    "status": "Up 2 hours",
                    "uptime_seconds": 7200.0,
                }
            ]

    monkeypatch.setattr("backend.services.docker_manager.get_docker_manager", lambda: FakeDM())

    token = billing_user_id.set("free_docker")
    try:
        before = svc.get_account("free_docker")["balance_credits"]
        charges = tracker.settle_tick("free_docker")
        assert len(charges) == 1
        rate = get_effective_hourly_rate("frontend", "free")
        expected_credits = charges[0]["delta_hours"] * rate * 1000
        assert charges[0]["credits"] == pytest.approx(expected_credits, rel=1e-3)
        after = svc.get_account("free_docker")["balance_credits"]
        assert after < before
    finally:
        billing_user_id.reset(token)
        reset_docker_billing_tracker(None)


def test_billing_overview_docker_plan_fields(billing_store, monkeypatch):
    from backend.billing.docker_meter import DockerBillingTracker, reset_docker_billing_tracker

    reset_docker_billing_tracker(DockerBillingTracker())
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "docker_overview")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "docker_secret")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "docker_overview", "password": "docker_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"]}
        resp = client.get("/billing", headers=headers)
        body = resp.json()
        assert resp.status_code == 200
        assert len(body["plans"]) >= 5
        docker = body["docker"]
        assert docker["plan_id"] == "free"
        assert "plan_terms" in docker
        assert docker["plan_terms"]["rate_multiplier"] == 2.0
        assert "included_hours_remaining" in docker["plan_terms"]
        assert "projected_billable_hourly_credits" in docker
        assert "docker_tiers" in body["rate_card"]


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
        assert len(body["plans"]) >= 5
        topup = client.post("/billing/topup", headers=headers, json={"credits": 500})
        assert topup.status_code == 200


def test_contributor_api_bind_lock_convert(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "contrib_user")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "contrib_secret")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    pools = get_pool_store()
    pools.credit_pool("contrib_user", POOL_CONTRIBUTION_UNLOCKED, 200, source="reward", origin="test")

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "contrib_user", "password": "contrib_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"]}

        bind = client.post(
            "/billing/contributor/bind-key",
            headers=headers,
            json={"encrypted_key": "sk-test-key-12345678", "vendor_id": "self_host"},
        )
        assert bind.status_code == 200
        assert bind.json()["status"] == "active"

        earnings = client.get("/billing/contributor/earnings", headers=headers)
        assert earnings.status_code == 200
        assert earnings.json()["unlocked_earnings"] == 200

        status = client.get("/billing/contributor/contribution/status", headers=headers)
        assert status.status_code == 200
        assert status.json()["unlocked"] == 200

        lock = client.post(
            "/billing/contributor/contribution/lock",
            headers=headers,
            json={"amount": 100, "lock_days": 30},
        )
        assert lock.status_code == 200
        assert lock.json()["locked_amount"] == 100

        convert = client.post("/billing/contribution/convert?amount=50", headers=headers)
        assert convert.status_code == 200
        assert convert.json()["converted"] == 50

        pools_resp = client.get("/billing/pools", headers=headers)
        assert pools_resp.status_code == 200
        assert "balances" in pools_resp.json()

        grants = client.get("/billing/grants", headers=headers)
        assert grants.status_code == 200
        assert len(grants.json()["items"]) >= 1


def test_billing_pools_in_snapshot(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "pool_user")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "pool_secret")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", billing_store.db_path)

    from backend.main import app

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"username": "pool_user", "password": "pool_secret"})
        headers = {"X-Linkin-Gate": login.json()["token"]}
        resp = client.get("/billing", headers=headers)
        body = resp.json()
        assert "pools" in body
        assert "contribution" in body
        assert "rollover_notice_zh" in body["pools"] or body["pools"].get("rollover_notice_zh")
        assert "vendor_preference" in body
