"""敘事工作區磁碟持久化測試。"""

from __future__ import annotations

import pytest

from backend.linkin.narrative_registry import (
    get_narrative_registry,
    reset_narrative_registry,
    restart_narrative_registry,
)
from backend.linkin.narrative_workspace import WorkspaceState


@pytest.fixture()
def persist_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    reset_narrative_registry()
    yield tmp_path
    reset_narrative_registry()


def test_workspace_save_load_roundtrip(persist_env):
    reg = get_narrative_registry()
    ws = reg.begin("task-persist-1", "snap-a")
    verdict = reg.write_draft(ws.workspace_id, "quest", {"title": "持久化任務"})
    assert verdict.ok is True

    ws_id = ws.workspace_id
    restart_narrative_registry()

    reg2 = get_narrative_registry()
    loaded = reg2.get(ws_id)
    assert loaded is not None
    assert loaded.task_id == "task-persist-1"
    assert loaded.snapshot_id == "snap-a"
    assert loaded.state == WorkspaceState.ACTIVE
    assert loaded.drafts["quest"]["title"] == "持久化任務"


def test_committed_workspace_not_reloaded(persist_env):
    reg = get_narrative_registry()
    ws = reg.begin("task-commit", "snap-b")
    reg.write_draft(ws.workspace_id, "npc", {"name": "測試 NPC"})
    reg.commit(ws.workspace_id, lambda drafts: drafts)
    ws_id = ws.workspace_id

    restart_narrative_registry()
    reg2 = get_narrative_registry()
    assert reg2.get(ws_id) is None


def test_awaiting_confirmation_survives_restart(persist_env):
    reg = get_narrative_registry()
    ws = reg.begin("task-refresh", "snap-old")
    reg.write_draft(ws.workspace_id, "story_arc", {"title": "草稿保留"})
    reg.on_l0_refresh("snap-new")
    ws_id = ws.workspace_id

    restart_narrative_registry()
    reg2 = get_narrative_registry()
    loaded = reg2.get(ws_id)
    assert loaded is not None
    assert loaded.state == WorkspaceState.AWAITING_CONFIRMATION
    assert loaded.drafts["story_arc"]["title"] == "草稿保留"
