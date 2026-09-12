"""敘事草稿工作區 REST（契約 C-L0-004）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.linkin.narrative_commit import KNOWN_DRAFT_KEYS, commit_narrative_drafts
from backend.linkin.narrative_registry import get_narrative_registry
from backend.linkin.narrative_starter import generate_starter_pack
from backend.linkin.narrative_workspace import (
    ERR_CONFIRM_CHOICE_INVALID,
    ERR_SNAPSHOT_UNRESOLVED,
    ERR_WORKSPACE_NOT_ACTIVE,
    ERR_WORKSPACE_UNKNOWN,
    EphemeralWorkspace,
    WorkspaceVerdict,
)

narrative_router = APIRouter(prefix="/linkin/narrative/workspaces", tags=["linkin-narrative"])


def _workspace_summary(ws: EphemeralWorkspace) -> dict[str, Any]:
    return ws.to_dict()


def _workspace_detail(ws: EphemeralWorkspace) -> dict[str, Any]:
    return {**ws.to_dict(), "drafts": dict(ws.drafts)}


def _raise_verdict(verdict: WorkspaceVerdict) -> None:
    code = verdict.error_code or ERR_WORKSPACE_UNKNOWN
    detail = {"ok": False, "error_code": code}
    if verdict.workspace is not None:
        detail["workspace"] = _workspace_summary(verdict.workspace)
    if code == ERR_WORKSPACE_UNKNOWN:
        raise HTTPException(status_code=404, detail=detail)
    if code in {ERR_SNAPSHOT_UNRESOLVED, ERR_WORKSPACE_NOT_ACTIVE}:
        raise HTTPException(status_code=409, detail=detail)
    raise HTTPException(status_code=400, detail=detail)


def _get_workspace_or_404(workspace_id: str) -> EphemeralWorkspace:
    ws = get_narrative_registry().get(workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error_code": ERR_WORKSPACE_UNKNOWN, "workspace_id": workspace_id},
        )
    return ws


@narrative_router.post("")
def begin_workspace(body: dict[str, Any]) -> dict[str, Any]:
    task_id = str(body.get("task_id") or body.get("taskId") or "").strip()
    snapshot_id = str(body.get("snapshot_id") or body.get("snapshotId") or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail={"message": "需要 task_id"})
    if not snapshot_id:
        raise HTTPException(status_code=400, detail={"message": "需要 snapshot_id"})
    ws = get_narrative_registry().begin(task_id, snapshot_id)
    return {"ok": True, "workspace": _workspace_detail(ws), "known_draft_keys": sorted(KNOWN_DRAFT_KEYS)}


@narrative_router.get("")
def list_workspaces(task_id: str = Query(default="")) -> dict[str, Any]:
    items = [_workspace_summary(ws) for ws in get_narrative_registry().list_for_task(task_id)]
    return {"workspaces": items, "count": len(items)}


@narrative_router.post("/refresh-l0")
def refresh_l0(body: dict[str, Any]) -> dict[str, Any]:
    new_snapshot_id = str(body.get("new_snapshot_id") or body.get("newSnapshotId") or "").strip()
    if not new_snapshot_id:
        raise HTTPException(status_code=400, detail={"message": "需要 new_snapshot_id"})
    affected = get_narrative_registry().on_l0_refresh(new_snapshot_id)
    return {"ok": True, "affected_workspace_ids": affected, "count": len(affected)}


@narrative_router.get("/{workspace_id}")
def get_workspace(workspace_id: str) -> dict[str, Any]:
    ws = _get_workspace_or_404(workspace_id)
    return {"ok": True, "workspace": _workspace_detail(ws), "known_draft_keys": sorted(KNOWN_DRAFT_KEYS)}


@narrative_router.put("/{workspace_id}/drafts/{key}")
def put_draft(workspace_id: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("value") if "value" in body else body
    verdict = get_narrative_registry().write_draft(workspace_id, key, value)
    if not verdict.ok:
        _raise_verdict(verdict)
    assert verdict.workspace is not None
    return {"ok": True, "workspace": _workspace_detail(verdict.workspace)}


@narrative_router.post("/{workspace_id}/draft")
def post_draft(workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    key = str(body.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail={"message": "需要 key"})
    if "value" not in body:
        raise HTTPException(status_code=400, detail={"message": "需要 value"})
    verdict = get_narrative_registry().write_draft(workspace_id, key, body["value"])
    if not verdict.ok:
        _raise_verdict(verdict)
    assert verdict.workspace is not None
    return {"ok": True, "workspace": _workspace_detail(verdict.workspace)}


@narrative_router.post("/{workspace_id}/starter-pack")
def seed_starter_pack(workspace_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """一鍵草案：LLM 或模板填充草稿，不自動 commit（Phase 0）。"""
    ws = _get_workspace_or_404(workspace_id)
    if ws.state.value != "active":
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error_code": ERR_WORKSPACE_NOT_ACTIVE, "workspace": _workspace_summary(ws)},
        )
    payload = body or {}
    region = str(payload.get("region") or "织庭都").strip() or "织庭都"
    theme = str(payload.get("theme") or payload.get("topic") or "靈丝残章").strip() or "靈丝残章"
    generated = generate_starter_pack(region=region, theme=theme)
    drafts = dict(generated.get("drafts") or {})
    reg = get_narrative_registry()
    for key, value in drafts.items():
        verdict = reg.write_draft(workspace_id, key, value)
        if not verdict.ok:
            _raise_verdict(verdict)
    refreshed = reg.get(workspace_id)
    assert refreshed is not None
    return {
        "ok": True,
        "source": generated.get("source") or "fallback",
        "workspace": _workspace_detail(refreshed),
        "draft_keys": sorted(refreshed.drafts.keys()),
    }


@narrative_router.post("/{workspace_id}/commit")
def commit_workspace(workspace_id: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}

    def _writer(drafts: dict[str, Any]) -> None:
        nonlocal summary
        summary = commit_narrative_drafts(drafts)

    verdict = get_narrative_registry().commit(workspace_id, writer=_writer)
    if not verdict.ok:
        _raise_verdict(verdict)
    assert verdict.workspace is not None
    return {
        "ok": True,
        "workspace": _workspace_summary(verdict.workspace),
        "committed": summary.get("committed") or {},
        "errors": summary.get("errors") or [],
    }


@narrative_router.post("/{workspace_id}/confirm")
def confirm_workspace(workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    choice = str(body.get("choice") or "").strip()
    new_snapshot_id = str(body.get("new_snapshot_id") or body.get("newSnapshotId") or "").strip()
    verdict = get_narrative_registry().confirm(workspace_id, choice, new_snapshot_id=new_snapshot_id)
    if not verdict.ok:
        _raise_verdict(verdict)
    assert verdict.workspace is not None
    return {"ok": True, "workspace": _workspace_detail(verdict.workspace)}


def register_narrative_routes(app) -> None:
    app.include_router(narrative_router)


__all__ = ["narrative_router", "register_narrative_routes"]
