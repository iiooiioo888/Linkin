"""post_company_reflect 配置與 API、完成事件欄位測試。"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.core.post_company_reflect import (
    post_company_reflect_mode,
    post_company_reflect_resolution,
)
from backend.main import app
from backend.services.task_manager import TaskManager, TaskRecord


@pytest.fixture
def cost_speed_file(tmp_path, monkeypatch):
    path = tmp_path / "cost_speed.json"
    path.write_text(
        json.dumps({
            "enabled": True,
            "post_company_reflect": "evaluate",
            "routing_feedback": {"feedback_enabled": True},
            "complexity": {},
            "stage_models": {},
            "models": {},
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(path))
    monkeypatch.delenv("EVOL_POST_COMPANY_REFLECT", raising=False)
    monkeypatch.delenv("EVOL_SKIP_POST_COMPANY_REFLECT", raising=False)
    from backend.core.cost_speed_router import reload_cost_speed

    reload_cost_speed()
    return path


def test_config_default_when_env_unset(cost_speed_file):
    assert post_company_reflect_mode() == "evaluate"
    assert post_company_reflect_resolution()["source"] == "config"


def test_env_overrides_config(cost_speed_file, monkeypatch):
    monkeypatch.setenv("EVOL_POST_COMPANY_REFLECT", "full")
    assert post_company_reflect_mode() == "full"
    assert post_company_reflect_resolution()["source"] == "env"


def test_put_get_post_company_reflect_api(cost_speed_file):
    client = TestClient(app)
    got = client.get("/config/cost-speed/post-company-reflect")
    assert got.status_code == 200
    assert got.json()["config"] == "evaluate"
    put = client.put("/config/cost-speed/post-company-reflect", json={"mode": "full"})
    assert put.status_code == 200
    assert put.json()["config"] == "full"
    assert post_company_reflect_mode() == "full"


def test_task_finished_simple_reflect_mode_not_applicable(monkeypatch):
    payloads: list[dict] = []
    mgr = TaskManager()
    record = TaskRecord("t1", "q", "simple", "quick_task")
    record.resolved_path = "simple"
    record.status = "completed"
    record.score = 8.5
    record.iteration = 1
    monkeypatch.setenv("EVOL_POST_COMPANY_REFLECT", "full")

    def _capture(_task_id: str, event: str, data: dict):
        if event == "task_finished":
            payloads.append(data)

    monkeypatch.setattr(mgr, "_broadcast_event", _capture)
    mgr._finish(record)
    assert payloads[0]["reflect_mode"] == "not_applicable"
    assert payloads[0]["score"] == 8.5


def test_task_finished_company_reflect_mode_from_applied(monkeypatch):
    monkeypatch.setenv("EVOL_POST_COMPANY_REFLECT", "full")
    mgr = TaskManager()
    record = TaskRecord("t2", "q", "company", "quick_task")
    record.resolved_path = "company"
    record.post_company_reflect_applied = "evaluate"
    record.status = "completed"
    payloads: list[dict] = []
    monkeypatch.setattr(
        mgr,
        "_broadcast_event",
        lambda _tid, ev, data: payloads.append(data) if ev == "task_finished" else None,
    )
    mgr._finish(record)
    assert payloads[0]["reflect_mode"] == "evaluate"


def test_put_post_company_reflect_requires_gate_when_forced(monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "alice")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "s3cret-test")
    monkeypatch.delenv("LINKIN_AUTH_DISABLED", raising=False)
    from backend.main import app

    with TestClient(app) as client:
        resp = client.put(
            "/config/cost-speed/post-company-reflect",
            json={"mode": "off"},
        )
        assert resp.status_code == 401
