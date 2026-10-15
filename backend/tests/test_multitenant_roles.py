"""多租戶角色／任務／記憶隔離驗收。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.company.role_catalog import (
    create_custom_role,
    get_monitor_prefs,
    get_snapshot,
    reset_catalog_cache,
    update_monitor_prefs,
    update_role_settings,
)
from backend.tenant.context import tenant_user_id
from backend.tenant.ids import LEGACY_CATALOG_OWNER
from backend.tenant.tasks import task_id_visible_for_tenant, task_visible_for_tenant


@pytest.fixture
def catalog_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("EVOL_ROLE_CATALOG_PATH", raising=False)
    monkeypatch.setenv("EVOL_ROLE_CATALOG_DIR", str(tmp_path / "catalogs"))
    reset_catalog_cache()
    yield
    reset_catalog_cache()


def test_role_catalog_isolated_per_user(catalog_dir):
    t_a = tenant_user_id.set("tenant_a")
    try:
        create_custom_role({"id": "only_a", "name": "A 專屬"})
        update_role_settings("manager", {"notes": "A 改過"})
        prefs_a = update_monitor_prefs({"poll_interval_ms": 7000})
        assert prefs_a["poll_interval_ms"] == 7000
    finally:
        tenant_user_id.reset(t_a)

    t_b = tenant_user_id.set("tenant_b")
    try:
        assert get_snapshot("custom_only_a") is None
        mgr = get_snapshot("manager")
        assert mgr is not None
        assert (mgr.get("notes") or "") != "A 改過"
        prefs_b = get_monitor_prefs()
        assert prefs_b["poll_interval_ms"] != 7000
        create_custom_role({"id": "only_b", "name": "B 專屬"})
    finally:
        tenant_user_id.reset(t_b)

    t_a2 = tenant_user_id.set("tenant_a")
    try:
        assert get_snapshot("custom_only_b") is None
        assert get_snapshot("custom_only_a") is not None
        assert get_snapshot("manager")["notes"] == "A 改過"
    finally:
        tenant_user_id.reset(t_a2)


def test_task_not_visible_across_tenants():
    rec = SimpleNamespace(user_id="alice")
    assert task_visible_for_tenant(rec, "alice")
    assert not task_visible_for_tenant(rec, "bob")


def test_legacy_empty_user_id_visibility(monkeypatch):
    legacy = SimpleNamespace(user_id="")
    assert task_visible_for_tenant(legacy, LEGACY_CATALOG_OWNER)
    assert task_visible_for_tenant(legacy, "dev")
    assert not task_visible_for_tenant(legacy, "anonymous")
    assert not task_visible_for_tenant(legacy, "")
    assert not task_visible_for_tenant(legacy, "random_user")

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert task_visible_for_tenant(legacy, LEGACY_CATALOG_OWNER)
    assert not task_visible_for_tenant(legacy, "dev")


def _tenant_headers(user_id: str) -> dict[str, str]:
    return {"X-Linkin-Tenant-Override": user_id}


def test_http_get_task_and_trace_cross_tenant_404(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services.task_manager import TaskManager, TaskRecord

    tm = TaskManager()
    rec = TaskRecord("trace_t1", "hello", "auto", "quick_task")
    rec.user_id = "alice"
    tm.tasks["trace_t1"] = rec
    monkeypatch.setattr("backend.services.task_manager.task_manager", tm)
    monkeypatch.setattr("backend.main.task_manager", tm)

    with TestClient(app) as client:
        ok = client.get("/tasks/trace_t1", headers=_tenant_headers("alice"))
        assert ok.status_code == 200

        deny = client.get("/tasks/trace_t1", headers=_tenant_headers("bob"))
        assert deny.status_code == 404

        trace = client.get("/tasks/trace_t1/trace", headers=_tenant_headers("bob"))
        assert trace.status_code == 404

        ctx = client.get("/tasks/trace_t1/context", headers=_tenant_headers("bob"))
        assert ctx.status_code == 404

        ckpt = client.get("/tasks/trace_t1/checkpoint", headers=_tenant_headers("bob"))
        assert ckpt.status_code == 404


def test_http_traces_list_scoped(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services.task_manager import TaskManager, TaskRecord

    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "trace_alice_only.jsonl").write_text(
        '{"ts":"2026-01-01T00:00:00+00:00","event":"phase"}\n',
        encoding="utf-8",
    )
    (trace_dir / "trace_bob_only.jsonl").write_text(
        '{"ts":"2026-01-01T00:00:00+00:00","event":"phase"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EVOL_TRACE_DIR", str(trace_dir))

    tm = TaskManager()
    tm.tasks["alice_only"] = TaskRecord("alice_only", "q", "auto", "t")
    tm.tasks["alice_only"].user_id = "alice"
    tm.tasks["bob_only"] = TaskRecord("bob_only", "q", "auto", "t")
    tm.tasks["bob_only"].user_id = "bob"
    monkeypatch.setattr("backend.services.task_manager.task_manager", tm)
    monkeypatch.setattr("backend.main.task_manager", tm)

    with TestClient(app) as client:
        data = client.get("/traces", headers=_tenant_headers("alice")).json()
        ids = {t["task_id"] for t in data["traces"]}
        assert "alice_only" in ids
        assert "bob_only" not in ids


def test_auth_gate_unauthorized_401(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.delenv("LINKIN_AUTH_DISABLED", raising=False)

    with TestClient(app) as client:
        resp = client.get("/monitor/agents")
        assert resp.status_code == 401


def test_http_skills_list_applies_override(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.company.skill_overrides import set_skill_enabled_override
    from backend.company.skills import Skill, skills_store
    from backend.main import app

    monkeypatch.setenv("EVOL_SKILLS_OVERRIDE_DIR", str(tmp_path / "ovr"))
    skills_store._skills.clear()
    skills_store._loaded = True
    skills_store._skills["demo"] = Skill(id="demo", name="Demo", content="x", enabled=True)

    t = tenant_user_id.set("skills_http")
    try:
        set_skill_enabled_override("demo", False)
    finally:
        tenant_user_id.reset(t)

    with TestClient(app) as client:
        row = client.get("/skills", headers=_tenant_headers("skills_http")).json()
        demo = next(s for s in row["skills"] if s["id"] == "demo")
        assert demo["enabled"] is False


def test_role_memory_collection_per_user(monkeypatch):
    from backend.company.role_memory import get_role_memory
    from backend.memory.vector_store import VectorMemoryStore

    class _FakeStore(VectorMemoryStore):
        def __init__(self, collection_name: str = ""):
            self.collection_name = collection_name

    monkeypatch.setattr("backend.company.role_memory.VectorMemoryStore", _FakeStore)

    t_a = tenant_user_id.set("mem_a")
    try:
        ma = get_role_memory("developer")
    finally:
        tenant_user_id.reset(t_a)

    t_b = tenant_user_id.set("mem_b")
    try:
        mb = get_role_memory("developer")
    finally:
        tenant_user_id.reset(t_b)

    assert ma.collection_name != mb.collection_name
    assert "mem_a" in ma.collection_name
    assert "mem_b" in mb.collection_name


def test_skill_override_per_tenant(tmp_path, monkeypatch):
    from backend.company.skill_overrides import set_skill_enabled_override, skill_enabled_override
    from backend.company.skills import Skill, skills_store

    monkeypatch.setenv("EVOL_SKILLS_OVERRIDE_DIR", str(tmp_path / "skill_ovr"))
    skills_store._skills.clear()
    skills_store._loaded = True
    skills_store._skills["demo"] = Skill(
        id="demo",
        name="Demo",
        content="body",
        enabled=True,
    )

    t_a = tenant_user_id.set("sk_a")
    try:
        set_skill_enabled_override("demo", False)
        assert skill_enabled_override("demo") is False
    finally:
        tenant_user_id.reset(t_a)

    t_b = tenant_user_id.set("sk_b")
    try:
        assert skill_enabled_override("demo") is None
        assert skills_store.enabled_for(None)
    finally:
        tenant_user_id.reset(t_b)
