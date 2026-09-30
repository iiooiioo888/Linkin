"""OPC 失敗必須留下狀態標記，並讓 /health 的 degraded 為真。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.company_nodes import enhance_with_opc_context
from backend.core.opc_degrade import note_opc_unavailable, opc_health_view, reset_opc_health
from opc_service.sense import OPCUnavailableError, sense_opc


@pytest.fixture(autouse=True)
def _reset_opc_flag():
    reset_opc_health()
    yield
    reset_opc_health()


@pytest.mark.asyncio
async def test_sense_failure_is_explicit_and_visible_on_health(monkeypatch):
    async def boom(_state):
        raise OPCUnavailableError("connection refused")

    monkeypatch.setattr("opc_service.sense.sense_opc", boom)
    result = await enhance_with_opc_context({"query": "讀取反應釜溫度"})

    assert result["opc_context"]["opc_status"] == "unavailable"
    assert result["opc_context"]["reason"] == "connection refused"
    assert opc_health_view()["opc_status"] == "unavailable"

    from backend.main import app

    with TestClient(app) as client:
        body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["degraded"] is True
    assert body["opc"]["opc_status"] == "unavailable"
    assert body["opc"]["reason"] == "connection refused"


@pytest.mark.asyncio
async def test_non_industrial_query_does_not_degrade_health():
    result = await enhance_with_opc_context({"query": "什麼是 Python？"})
    assert result["opc_context"]["opc_status"] == "not_required"
    assert opc_health_view() == {"opc_status": "ok", "reason": ""}

    note_opc_unavailable("先前故障")
    again = await enhance_with_opc_context({"query": "什麼是 Python？"})
    assert again["opc_context"]["opc_status"] == "not_required"
    assert opc_health_view()["opc_status"] == "unavailable"


@pytest.mark.asyncio
async def test_successful_reading_clears_degraded(monkeypatch):
    note_opc_unavailable("先前故障")

    async def ok(_state):
        return {
            "opc_readings": {"T1": {"value": 36.5, "quality": "Good"}},
            "opc_status": "available",
        }

    monkeypatch.setattr("opc_service.sense.sense_opc", ok)
    result = await enhance_with_opc_context({"query": "目前溫度"})
    assert result["opc_context"]["opc_status"] == "available"
    assert "T1" in result["opc_context"]["summary"]
    assert opc_health_view() == {"opc_status": "ok", "reason": ""}


@pytest.mark.asyncio
async def test_sense_opc_marks_transport_failure(monkeypatch):
    async def fail(_tags):
        raise OPCUnavailableError("down")

    monkeypatch.setattr("opc_service.sense.OPC_TIER", "cloud")
    monkeypatch.setattr("opc_service.sense._read_opc_tags", fail)
    result = await sense_opc({})
    assert result["opc_status"] == "unavailable"
    assert result["opc_readings"] == {}
    assert result["opc_reason"] == "down"
