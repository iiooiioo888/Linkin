"""多租戶角色／任務／記憶隔離驗收。"""

from __future__ import annotations

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
from backend.tenant.tasks import task_visible_for_tenant


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
    from types import SimpleNamespace

    rec = SimpleNamespace(user_id="alice")
    assert task_visible_for_tenant(rec, "alice")
    assert not task_visible_for_tenant(rec, "bob")


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
