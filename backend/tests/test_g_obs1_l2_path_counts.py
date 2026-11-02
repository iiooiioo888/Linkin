"""G-OBS1 L2：path_counts 結構化 log／內部讀點／runbook 契約測。"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.modelgw.api import (
    _is_path_counts_client_allowed,
    register_modelgw,
)
from backend.modelgw.runtime import (
    _bump,
    path_counts,
    path_counts_snapshot,
    reset_path_counts,
)

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "ops" / "g-obs1-path-counts-runbook.md"
CONTRACT = REPO / "docs" / "contracts" / "g-obs1-l2-path-counts.md"
AGG_SCRIPT = REPO / "backend" / "scripts" / "aggregate_g_obs1_path_counts.py"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MODELGW_WIRE_MODE", "enforce")
    monkeypatch.delenv("MODELGW_PATH_COUNTS_TOKEN", raising=False)
    monkeypatch.delenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE", raising=False)
    monkeypatch.delenv("MODELGW_WORKERS_HINT", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    reset_path_counts()
    app = FastAPI()
    register_modelgw(app)
    with TestClient(app) as c:
        yield c
    reset_path_counts()


# --- C1：結構化 log ---


def test_bump_emits_g_obs1_structured_log(caplog):
    reset_path_counts()
    with caplog.at_level(logging.INFO, logger="backend.modelgw.runtime"):
        _bump("via")
        _bump("would_block")
        _bump("bypass")
    msgs = [r.message for r in caplog.records]
    assert any("g_obs1_path_event=1" in m and "path=via" in m for m in msgs)
    assert any("g_obs1_path_event=1" in m and "path=would_block" in m for m in msgs)
    assert any("g_obs1_path_event=1" in m and "path=bypass" in m for m in msgs)
    assert path_counts()["via"] == 1
    assert path_counts()["would_block"] == 1
    assert path_counts()["bypass"] == 1


def test_aggregate_script_counts_events(tmp_path):
    log = tmp_path / "sample.log"
    log.write_text(
        (
            "INFO MODELGW g_obs1_path_event=1 path=via count=1 pid=1 wire_mode=enforce\n"
            "noise\n"
            "INFO MODELGW g_obs1_path_event=1 path=via count=2 pid=1 wire_mode=enforce\n"
            "INFO MODELGW g_obs1_path_event=1 path=bypass count=1 pid=1 wire_mode=off\n"
            "INFO MODELGW g_obs1_path_event=1 path=would_block count=1 pid=1 wire_mode=enforce\n"
        ),
        encoding="utf-8",
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "aggregate_g_obs1_path_counts", AGG_SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.aggregate_lines(log.read_text(encoding="utf-8").splitlines())
    assert result["via"] == 2
    assert result["bypass"] == 1
    assert result["would_block"] == 1
    assert result["events_total"] == 4


# --- C2：讀點 shape／閘 ---


def test_path_counts_snapshot_shape(monkeypatch):
    reset_path_counts()
    _bump("via")
    snap = path_counts_snapshot()
    for key in (
        "via",
        "bypass",
        "would_block",
        "pid",
        "started_at",
        "wire_mode",
        "scope",
        "multi_worker_incomplete",
        "workers_hint",
    ):
        assert key in snap
    assert snap["scope"] == "since_process_start"
    assert snap["via"] == 1
    assert snap["multi_worker_incomplete"] is False
    assert isinstance(snap["pid"], int)
    assert snap["started_at"]


def test_readpoint_ok_with_token_on_testclient(client, monkeypatch):
    """TestClient host 非 IP → 需 token。"""
    monkeypatch.setenv("MODELGW_PATH_COUNTS_TOKEN", "secret-l2")
    reset_path_counts()
    _bump("via")
    _bump("would_block")
    resp = client.get(
        "/api/internal/modelgw/path-counts",
        headers={"X-ModelGW-Internal-Token": "secret-l2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["via"] == 1
    assert body["would_block"] == 1
    assert body["bypass"] == 0
    assert "pid" in body and "started_at" in body and "wire_mode" in body
    assert body["scope"] == "since_process_start"
    assert body["hub_metrics_is_not_path_counts"] is True
    # 讀點不得清零
    assert path_counts()["via"] == 1


def test_readpoint_forbidden_without_token_on_testclient(client, monkeypatch):
    monkeypatch.delenv("MODELGW_PATH_COUNTS_TOKEN", raising=False)
    resp = client.get("/api/internal/modelgw/path-counts")
    assert resp.status_code == 403
    assert resp.json()["code"] == "PATH_COUNTS_FORBIDDEN"


def test_readpoint_forbidden_wrong_token(client, monkeypatch):
    monkeypatch.setenv("MODELGW_PATH_COUNTS_TOKEN", "secret-l2")
    resp = client.get(
        "/api/internal/modelgw/path-counts",
        headers={"X-ModelGW-Internal-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_loopback_allowed_without_token(monkeypatch):
    monkeypatch.delenv("MODELGW_PATH_COUNTS_TOKEN", raising=False)
    monkeypatch.delenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE", raising=False)

    class _C:
        def __init__(self, host: str):
            self.host = host

    class _R:
        def __init__(self, host: str):
            self.client = _C(host)
            self.headers: dict[str, str] = {}

    assert _is_path_counts_client_allowed(_R("127.0.0.1")) is True
    assert _is_path_counts_client_allowed(_R("::1")) is True


def test_public_ip_forbidden_without_token(monkeypatch):
    monkeypatch.delenv("MODELGW_PATH_COUNTS_TOKEN", raising=False)

    class _C:
        def __init__(self, host: str):
            self.host = host

    class _R:
        def __init__(self, host: str):
            self.client = _C(host)
            self.headers: dict[str, str] = {}

    assert _is_path_counts_client_allowed(_R("8.8.8.8")) is False


def test_private_requires_flag_or_token(monkeypatch):
    monkeypatch.delenv("MODELGW_PATH_COUNTS_TOKEN", raising=False)
    monkeypatch.delenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE", raising=False)

    class _C:
        def __init__(self, host: str):
            self.host = host

    class _R:
        def __init__(self, host: str, token: str | None = None):
            self.client = _C(host)
            self.headers: dict[str, str] = {}
            if token:
                self.headers["X-ModelGW-Internal-Token"] = token

    assert _is_path_counts_client_allowed(_R("10.0.0.5")) is False
    monkeypatch.setenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE", "1")
    assert _is_path_counts_client_allowed(_R("10.0.0.5")) is True
    monkeypatch.delenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE", raising=False)
    monkeypatch.setenv("MODELGW_PATH_COUNTS_TOKEN", "t")
    assert _is_path_counts_client_allowed(_R("10.0.0.5", token="t")) is True


def test_multi_worker_incomplete_flag(monkeypatch):
    monkeypatch.setenv("MODELGW_WORKERS_HINT", "2")
    snap = path_counts_snapshot()
    assert snap["multi_worker_incomplete"] is True
    assert snap["workers_hint"] == 2


def test_readpoint_does_not_call_reset(client, monkeypatch):
    monkeypatch.setenv("MODELGW_PATH_COUNTS_TOKEN", "secret-l2")
    reset_path_counts()
    _bump("bypass")
    before = path_counts()
    for _ in range(3):
        assert (
            client.get(
                "/api/internal/modelgw/path-counts",
                headers={"X-ModelGW-Internal-Token": "secret-l2"},
            ).status_code
            == 200
        )
    assert path_counts() == before


# --- C3／C4：runbook／契約文件 ---


def test_runbook_exists_with_required_sections():
    assert RUNBOOK.is_file()
    text = RUNBOOK.read_text(encoding="utf-8")
    required = [
        "指標語義",
        "如何讀",
        "誰讀",
        "告警",
        "rollback",
        "L1",
        "單 worker",
        "multi_worker_incomplete",
        "path_counts_ne_closed",
        "/api/internal/modelgw/path-counts",
        "g_obs1_path_event=1",
        "不得自動關 L1",
    ]
    for needle in required:
        assert needle in text, f"missing section/keyword: {needle}"


def test_contract_doc_flags():
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8")
    assert "G-OBS1" in text
    assert "ready_to_merge=false" in text
    assert "wire_change=none" in text
    assert "l1_continue=true" in text
    assert "path_counts_ne_closed=true" in text
