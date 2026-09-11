"""靈境積分商業計費：方案、計量、配額、功能包閘門。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.billing.context import billing_user_id
from backend.billing.credits import credits_for_llm_tokens, credits_for_raho_layer
from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
from backend.billing.metering import meter_llm, meter_raho_layer, meter_quant_call, require_feature
from backend.billing.plans import PACK_QUANT, plan_has_feature
from backend.billing.quota import BillingService, reset_billing_service
from backend.billing.store import BillingStore, reset_billing_store


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
