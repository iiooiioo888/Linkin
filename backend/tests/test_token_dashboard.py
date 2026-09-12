"""Token 用量看板：Linkin 計費庫 adapter 與 HTTP 端點。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.billing.metering import meter_llm
from backend.billing.quota import BillingService, get_billing_service, reset_billing_service
from backend.billing.store import BillingStore, reset_billing_store
from backend.billing.task_lifecycle import begin_billed_task, record_llm_usage
from backend.billing.token_dashboard.adapter import collect_linkin_usage, dashboard_stats
from backend.billing.token_dashboard.service import generate_token_dashboard_html
from backend.main import app


@pytest.fixture()
def billing_store(tmp_path, monkeypatch):
    db = str(tmp_path / "billing_token_dash.sqlite3")
    monkeypatch.setenv("LINKIN_BILLING_FORCE", "1")
    monkeypatch.setenv("LINKIN_BILLING_DB", db)
    store = BillingStore(db_path=db)
    reset_billing_store(store)
    reset_billing_service(BillingService(store))
    yield store
    reset_billing_store(None)
    reset_billing_service(None)


def _seed_llm_usage(user_id: str) -> None:
    get_billing_service().ensure_account(user_id, "free")
    begun = begin_billed_task(user_id, baseline_tokens=500, iterations=1, roles=1, model="gpt-test")
    record_llm_usage(
        begun["task_id"],
        input_tokens=1200,
        output_tokens=300,
        cache_read_tokens=100,
        model="gpt-test",
        role="assistant",
    )
    meter_llm(
        "claude-test",
        800,
        200,
        user_id=user_id,
        reference="chat-session-1",
        cache_read_tokens=50,
    )


def test_collect_linkin_usage_from_pool_and_usage_events(billing_store):
    _seed_llm_usage("alice")
    data = collect_linkin_usage("alice", days=30)
    stats = dashboard_stats(data)
    assert stats["requests"] >= 1
    assert stats["total_tokens"] > 0
    assert isinstance(data["sess"], list)
    assert data["models"]
    assert "Linkin" in str(data.get("source", ""))


def test_collect_linkin_usage_empty_honest(billing_store):
    get_billing_service().ensure_account("nobody", "free")
    data = collect_linkin_usage("nobody", days=7)
    stats = dashboard_stats(data)
    assert stats["empty"] is True
    assert stats["requests"] == 0
    assert data["sess"] == []


def test_generate_token_dashboard_html(billing_store):
    _seed_llm_usage("bob")
    html = generate_token_dashboard_html("bob", days=30)
    assert "<title>Token 消耗看板</title>" in html
    assert "Token 消耗看板" in html


def test_billing_token_dashboard_endpoints(billing_store, monkeypatch):
    monkeypatch.setenv("LINKIN_BILLING_ANONYMOUS_USER", "carol")
    _seed_llm_usage("carol")
    client = TestClient(app)
    resp = client.get("/billing/token-dashboard?days=30")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Token 消耗看板" in resp.text

    post = client.post("/billing/token-dashboard/generate?days=30")
    assert post.status_code == 200
    body = post.json()
    assert body["stats"]["requests"] >= 1
    assert body["dashboard_url"] == "/billing/token-dashboard"
    assert "Token 消耗看板" in body["html"]
