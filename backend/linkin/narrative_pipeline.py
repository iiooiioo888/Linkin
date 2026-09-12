"""Phase 5：敘事 RPG 一鍵管線編排器。

串接 Phase 0–4 既有模組，不重複業務邏輯。兩段式：
- ``confirm_world=false``：begin → generate → commit → map_generate → previews
- ``confirm_world=true``：在上述基礎上執行 build／world／map apply（橋接關閉時 dry-run）
"""

from __future__ import annotations

import time
from typing import Any, Literal

from backend.linkin.build_brief_apply import (
    BuildBriefError,
    apply_build_brief,
    get_build_brief,
    preview_build_brief,
)
from backend.linkin.knowledge import COL_EVENTS, get_store, list_entities, upsert_entity
from backend.linkin.map_plan import (
    MapPlanError,
    apply_map_plan,
    gather_narrative_context,
    generate_map_plan,
    preview_map_plan,
    validate_map_plan,
)
from backend.linkin.minecraft import monitor_status
from backend.linkin.narrative_commit import KNOWN_DRAFT_KEYS, commit_narrative_drafts
from backend.linkin.narrative_generate import NarrativeGenerateError, generate_narrative_drafts
from backend.linkin.narrative_registry import get_narrative_registry
from backend.linkin.narrative_starter import generate_starter_pack
from backend.linkin.narrative_world_apply import apply_world_intents, preview_world_intents
from backend.linkin.narrative_workspace import (
    ERR_SNAPSHOT_UNRESOLVED,
    ERR_WORKSPACE_NOT_ACTIVE,
    ERR_WORKSPACE_UNKNOWN,
    WorkspaceState,
)
from backend.linkin.tools import ToolValidationError

StepStatus = Literal["pending", "running", "ok", "error", "partial", "skipped"]

PIPELINE_STEP_ORDER = (
    "begin_workspace",
    "generate",
    "commit",
    "map_generate",
    "build_preview",
    "world_preview",
    "map_preview",
    "build_apply",
    "world_apply",
    "map_apply",
)

PREVIEW_STEPS = frozenset({"build_preview", "world_preview", "map_preview"})
APPLY_STEPS = frozenset({"build_apply", "world_apply", "map_apply"})

STEP_LABELS: dict[str, str] = {
    "begin_workspace": "建立工作區",
    "generate": "AI 生成草案",
    "commit": "提交至 Linkin",
    "map_generate": "生成區域地圖",
    "build_preview": "建築預覽",
    "world_preview": "世界意圖預覽",
    "map_preview": "地圖預覽",
    "build_apply": "落地建築",
    "world_apply": "落地 NPC／任務／道具",
    "map_apply": "落地地圖",
}


def _step(
    step_id: str,
    status: StepStatus,
    *,
    detail: dict[str, Any] | None = None,
    message: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": step_id,
        "label": STEP_LABELS.get(step_id, step_id),
        "status": status,
    }
    if message:
        row["message"] = message
    if detail:
        row["detail"] = detail
    return row


def _bridge_snapshot() -> dict[str, Any]:
    status = monitor_status()
    return {
        "enabled": status.get("enabled"),
        "connected": status.get("connected"),
        "dry_run": status.get("dry_run"),
        "world": status.get("world"),
    }


def _bridge_live() -> bool:
    status = monitor_status()
    return bool(status.get("enabled") and status.get("connected") and not status.get("dry_run"))


def _resolve_steps(options: dict[str, Any], *, confirm_world: bool) -> dict[str, bool]:
    raw = options.get("steps") if isinstance(options.get("steps"), dict) else {}
    enabled: dict[str, bool] = {}
    for step_id in PIPELINE_STEP_ORDER:
        if isinstance(raw, dict) and step_id in raw:
            enabled[step_id] = bool(raw[step_id])
        elif step_id in APPLY_STEPS:
            enabled[step_id] = confirm_world
        elif step_id in PREVIEW_STEPS:
            enabled[step_id] = not confirm_world
        else:
            enabled[step_id] = True
    return enabled


def _find_build_brief_id(committed: dict[str, Any]) -> str | None:
    brief = committed.get("build_brief")
    if isinstance(brief, dict) and brief.get("id"):
        return str(brief["id"])
    for item in list_entities("build_briefs"):
        if str(item.get("source") or "") == "narrative_workspace":
            return str(item.get("id") or "") or None
    return None


def run_narrative_pipeline(body: dict[str, Any]) -> dict[str, Any]:
    """執行一鍵敘事管線，回傳逐步狀態與彙總。"""
    started = time.time()
    reg = get_narrative_registry()
    bridge = _bridge_snapshot()

    brief = str(body.get("brief") or body.get("seed") or "").strip()
    workspace_id = str(body.get("workspace_id") or body.get("workspaceId") or "").strip()
    task_id = str(body.get("task_id") or body.get("taskId") or "").strip()
    snapshot_id = str(body.get("snapshot_id") or body.get("snapshotId") or "snap-local").strip() or "snap-local"
    region = str(body.get("region") or "织庭都").strip() or "织庭都"
    theme = str(body.get("theme") or body.get("topic") or "").strip()
    map_seed = str(body.get("seed") or body.get("map_seed") or theme or region).strip()
    locale = str(body.get("locale") or "zh-Hant").strip() or "zh-Hant"
    confirm_world = bool(body.get("confirm_world") or body.get("confirmWorld"))
    regenerate = bool(body.get("regenerate"))
    use_starter_pack = bool(body.get("use_starter_pack") or body.get("useStarterPack"))
    stop_on_error = bool(body.get("stop_on_error") or body.get("stopOnError"))

    enabled_steps = _resolve_steps(body.get("options") or {}, confirm_world=confirm_world)
    steps: list[dict[str, Any]] = [_step(step_id, "pending") for step_id in PIPELINE_STEP_ORDER]
    step_index = {row["id"]: idx for idx, row in enumerate(steps)}

    def _set(step_id: str, status: StepStatus, *, detail: dict[str, Any] | None = None, message: str = "") -> None:
        idx = step_index[step_id]
        steps[idx] = _step(step_id, status, detail=detail, message=message)

    for step_id in PIPELINE_STEP_ORDER:
        if not enabled_steps.get(step_id):
            _set(step_id, "skipped", message="此輪未啟用")

    def _skip_remaining(from_step: str, reason: str) -> None:
        try:
            start = PIPELINE_STEP_ORDER.index(from_step)
        except ValueError:
            return
        for step_id in PIPELINE_STEP_ORDER[start + 1 :]:
            if step_id in step_index and steps[step_index[step_id]]["status"] == "pending":
                _set(step_id, "skipped", message=reason)

    workspace = reg.get(workspace_id) if workspace_id else None
    committed: dict[str, Any] = {}
    commit_errors: list[dict[str, Any]] = []
    map_plan: dict[str, Any] | None = None
    map_preview: dict[str, Any] | None = None
    build_brief_id: str | None = None
    overall_status: StepStatus = "ok"
    needs_confirm = not confirm_world

    # ── begin_workspace ──────────────────────────────────────
    if enabled_steps.get("begin_workspace"):
        _set("begin_workspace", "running")
        if workspace is None:
            if not task_id:
                task_id = f"task-pipeline-{int(time.time())}"
            workspace = reg.begin(task_id, snapshot_id)
            workspace_id = workspace.workspace_id
            _set(
                "begin_workspace",
                "ok",
                detail={"workspace_id": workspace_id, "task_id": task_id, "snapshot_id": snapshot_id},
            )
        else:
            _set(
                "begin_workspace",
                "skipped",
                message="已提供 workspace_id",
                detail={"workspace_id": workspace.workspace_id},
            )
    elif workspace is None and workspace_id:
        workspace = reg.get(workspace_id)

    if workspace is None:
        return {
            "ok": False,
            "status": "error",
            "confirm_world": confirm_world,
            "needs_confirm": True,
            "bridge": bridge,
            "workspace_id": workspace_id or None,
            "steps": steps,
            "message": "無法解析工作區；請提供 workspace_id 或啟用 begin_workspace",
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    workspace_id = workspace.workspace_id
    if workspace.state == WorkspaceState.AWAITING_CONFIRMATION:
        return {
            "ok": False,
            "status": "error",
            "confirm_world": confirm_world,
            "needs_confirm": True,
            "bridge": bridge,
            "workspace_id": workspace_id,
            "workspace": workspace.to_dict(),
            "steps": steps,
            "error_code": ERR_SNAPSHOT_UNRESOLVED,
            "message": "工作區快照衝突，請先 confirm rebind 或 discard",
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    already_committed = workspace.state == WorkspaceState.COMMITTED

    # ── generate ─────────────────────────────────────────────
    if enabled_steps.get("generate"):
        _set("generate", "running")
        if already_committed and not regenerate:
            _set("generate", "skipped", message="工作區已提交；設定 regenerate=true 可重新生成")
        elif workspace.drafts and not regenerate and not brief:
            _set("generate", "skipped", message="已有草稿；設定 regenerate=true 可覆寫")
        else:
            if not brief and not use_starter_pack:
                _set("generate", "error", message="需要 brief 或 use_starter_pack=true")
                if stop_on_error:
                    _skip_remaining("generate", "generate 失敗")
            else:
                try:
                    if use_starter_pack:
                        generated = generate_starter_pack(region=region, theme=theme or "靈丝残章")
                        source = generated.get("source") or "fallback"
                    else:
                        generated = generate_narrative_drafts(
                            brief=brief,
                            locale=locale,
                            region=region,
                            theme=theme,
                        )
                        source = generated.get("source") or "llm"
                    drafts = dict(generated.get("drafts") or {})
                    written: list[str] = []
                    for key, value in drafts.items():
                        verdict = reg.write_draft(workspace_id, key, value)
                        if not verdict.ok:
                            raise RuntimeError(verdict.error_code or ERR_WORKSPACE_NOT_ACTIVE)
                        written.append(key)
                    workspace = reg.get(workspace_id)
                    assert workspace is not None
                    _set(
                        "generate",
                        "ok",
                        detail={"source": source, "replaced_keys": written},
                    )
                except NarrativeGenerateError as exc:
                    if exc.code == "llm_unavailable":
                        try:
                            generated = generate_starter_pack(region=region, theme=theme or brief or "靈丝残章")
                            drafts = dict(generated.get("drafts") or {})
                            for key, value in drafts.items():
                                reg.write_draft(workspace_id, key, value)
                            workspace = reg.get(workspace_id)
                            _set(
                                "generate",
                                "partial",
                                message="LLM 不可用，已改用本地模板草案",
                                detail={"source": "fallback", "replaced_keys": sorted(drafts.keys())},
                            )
                        except Exception as fallback_exc:
                            _set("generate", "error", message=str(fallback_exc))
                            if stop_on_error:
                                _skip_remaining("generate", "generate 失敗")
                    else:
                        _set("generate", "error", message=str(exc), detail={"code": exc.code})
                        if stop_on_error:
                            _skip_remaining("generate", "generate 失敗")
                except Exception as exc:
                    _set("generate", "error", message=str(exc))
                    if stop_on_error:
                        _skip_remaining("generate", "generate 失敗")

    workspace = reg.get(workspace_id)
    assert workspace is not None

    # ── commit ───────────────────────────────────────────────
    if enabled_steps.get("commit"):
        _set("commit", "running")
        if already_committed and not regenerate:
            _set("commit", "skipped", message="工作區已提交")
            build_brief_id = _find_build_brief_id({})
        elif not workspace.drafts:
            _set("commit", "error", message="無草稿可提交")
            if stop_on_error:
                _skip_remaining("commit", "commit 失敗")
        else:
            summary_holder: dict[str, Any] = {}

            def _writer(drafts: dict[str, Any]) -> None:
                summary_holder.update(commit_narrative_drafts(drafts))

            verdict = reg.commit(workspace_id, writer=_writer)
            if not verdict.ok:
                _set("commit", "error", message=verdict.error_code or ERR_WORKSPACE_UNKNOWN)
                if stop_on_error:
                    _skip_remaining("commit", "commit 失敗")
            else:
                committed = dict(summary_holder.get("committed") or {})
                commit_errors = list(summary_holder.get("errors") or [])
                build_brief_id = _find_build_brief_id(committed)
                status: StepStatus = "ok" if not commit_errors else "partial"
                _set(
                    "commit",
                    status,
                    detail={"committed": committed, "errors": commit_errors},
                    message=f"已提交 {len(committed)} 鍵" if committed else "",
                )
                workspace = reg.get(workspace_id)
                already_committed = True

    if build_brief_id is None:
        build_brief_id = _find_build_brief_id(committed)

    # ── map_generate ─────────────────────────────────────────
    if enabled_steps.get("map_generate"):
        _set("map_generate", "running")
        try:
            context = gather_narrative_context(workspace_drafts=dict(workspace.drafts), region=region)
            generated = generate_map_plan(context=context, seed=map_seed)
            map_plan = generated["plan"]
            map_preview = preview_map_plan(map_plan)
            saved = upsert_entity("map_plans", {**map_plan, "status": "planned"})
            map_plan = saved
            _set(
                "map_generate",
                "ok",
                detail={
                    "source": generated.get("source") or "fallback",
                    "plan_id": saved.get("id"),
                    "preview": map_preview,
                },
            )
        except MapPlanError as exc:
            _set("map_generate", "error", message=str(exc), detail={"code": exc.code})
            if stop_on_error:
                _skip_remaining("map_generate", "map_generate 失敗")
        except Exception as exc:
            _set("map_generate", "error", message=str(exc))
            if stop_on_error:
                _skip_remaining("map_generate", "map_generate 失敗")

    # ── previews (phase 1) ───────────────────────────────────
    if enabled_steps.get("build_preview"):
        _set("build_preview", "running")
        if not build_brief_id:
            _set("build_preview", "skipped", message="無 build_brief 可預覽")
        else:
            try:
                brief_entity = get_build_brief(build_brief_id)
                preview = preview_build_brief(brief_entity)
                _set(
                    "build_preview",
                    "ok",
                    detail={
                        "brief_id": build_brief_id,
                        "solid_count": preview.get("bounds", {}).get("solid_count"),
                        "dry_run": preview.get("dry_run"),
                    },
                )
            except BuildBriefError as exc:
                _set("build_preview", "error", message=str(exc), detail={"code": exc.code})
            except Exception as exc:
                _set("build_preview", "error", message=str(exc))

    if enabled_steps.get("world_preview"):
        _set("world_preview", "running")
        try:
            preview = preview_world_intents(apply_all=True)
            count = int(preview.get("count") or 0)
            if count == 0:
                _set("world_preview", "skipped", message="無待落地世界意圖")
            else:
                _set(
                    "world_preview",
                    "ok",
                    detail={"count": count, "intents": preview.get("intents")},
                )
        except Exception as exc:
            _set("world_preview", "error", message=str(exc))

    if enabled_steps.get("map_preview"):
        _set("map_preview", "running")
        if map_plan is None:
            _set("map_preview", "skipped", message="無 map_plan；請先 map_generate")
        else:
            try:
                preview = preview_map_plan(map_plan)
                map_preview = preview
                _set(
                    "map_preview",
                    "ok",
                    detail={"plan_id": map_plan.get("id"), "preview": preview},
                )
            except MapPlanError as exc:
                _set("map_preview", "error", message=str(exc), detail={"code": exc.code})
            except Exception as exc:
                _set("map_preview", "error", message=str(exc))

    # ── apply steps (phase 2, confirm_world) ─────────────────
    if not confirm_world:
        for step_id in APPLY_STEPS:
            if step_id in step_index:
                _set(step_id, "skipped", message="需要 confirm_world=true 才執行世界寫入")
    else:
        dry_run_build = not _bridge_live()

        if enabled_steps.get("build_apply"):
            _set("build_apply", "running")
            if not build_brief_id:
                _set("build_apply", "skipped", message="無 build_brief 可落地")
            else:
                try:
                    brief_entity = get_build_brief(build_brief_id)
                    result = apply_build_brief(brief_entity, dry_run=dry_run_build)
                    placement = result.get("placement") or {}
                    status: StepStatus = "ok" if placement.get("ok") else "partial"
                    if placement.get("dry_run"):
                        status = "partial" if status == "ok" else status
                    _set(
                        "build_apply",
                        status,
                        detail={
                            "brief_id": build_brief_id,
                            "placement": placement,
                            "dry_run": placement.get("dry_run") or dry_run_build,
                        },
                        message="乾跑模式" if placement.get("dry_run") or dry_run_build else "",
                    )
                except BuildBriefError as exc:
                    _set("build_apply", "error", message=str(exc), detail={"code": exc.code})
                except Exception as exc:
                    _set("build_apply", "error", message=str(exc))

        if enabled_steps.get("world_apply"):
            _set("world_apply", "running")
            try:
                result = apply_world_intents(apply_all=True, dry_run=False)
                summary = result.get("summary") or {}
                overall = str(summary.get("overall_status") or "failed")
                status_map = {"applied": "ok", "partial": "partial", "skipped": "skipped", "failed": "error"}
                _set(
                    "world_apply",
                    status_map.get(overall, "partial"),
                    detail={"summary": summary, "dry_run": result.get("dry_run")},
                )
            except Exception as exc:
                _set("world_apply", "error", message=str(exc))

        if enabled_steps.get("map_apply"):
            _set("map_apply", "running")
            if map_plan is None:
                _set("map_apply", "skipped", message="無 map_plan 可落地")
            else:
                try:
                    result = apply_map_plan(map_plan, confirmed=True)
                    validated = validate_map_plan(map_plan)
                    mcp_status = str(result.get("status") or "complete")
                    updated = upsert_entity(
                        "map_plans",
                        {
                            **validated,
                            "status": "applied"
                            if mcp_status == "complete"
                            else ("partial" if mcp_status == "partial" else "failed"),
                            "mcp": {
                                "ok": result.get("ok"),
                                "dry_run": result.get("dry_run"),
                                "blocks_placed": result.get("blocks_placed"),
                            },
                        },
                    )
                    map_plan = updated
                    get_store().upsert(
                        COL_EVENTS,
                        f"管線地圖落地 {validated['id']}（status={mcp_status}）",
                        {"kind": "minecraft", "map_plan_id": validated["id"], "status": mcp_status},
                        skip_quality=True,
                    )
                    apply_status: StepStatus = (
                        "ok" if mcp_status == "complete" else ("partial" if mcp_status == "partial" else "error")
                    )
                    if result.get("dry_run") and apply_status == "ok":
                        apply_status = "partial"
                    _set(
                        "map_apply",
                        apply_status,
                        detail={
                            "plan_id": validated.get("id"),
                            "minecraft": result,
                            "dry_run": result.get("dry_run"),
                        },
                    )
                except (MapPlanError, ToolValidationError) as exc:
                    code = getattr(exc, "code", "apply_failed")
                    _set("map_apply", "error", message=str(exc), detail={"code": code})
                except Exception as exc:
                    _set("map_apply", "error", message=str(exc))

    # ── aggregate ────────────────────────────────────────────
    terminal = [s for s in steps if s["status"] not in {"pending", "running"}]
    if any(s["status"] == "error" for s in terminal):
        overall_status = "error"
    elif any(s["status"] == "partial" for s in terminal):
        overall_status = "partial"
    elif terminal and all(s["status"] in {"ok", "skipped"} for s in terminal):
        overall_status = "ok"
    else:
        overall_status = "partial"

    workspace = reg.get(workspace_id)
    plan_for_confirm: dict[str, Any] = {}
    if needs_confirm:
        plan_for_confirm = {
            "confirm_world_required": True,
            "build_brief_id": build_brief_id,
            "map_plan_id": (map_plan or {}).get("id"),
            "pending_world_count": preview_world_intents(apply_all=True).get("count", 0),
            "message": "預覽完成。設定 confirm_world=true 以執行建築／世界／地圖落地。",
        }

    return {
        "ok": overall_status in {"ok", "partial"},
        "status": overall_status,
        "confirm_world": confirm_world,
        "needs_confirm": needs_confirm,
        "bridge": bridge,
        "workspace_id": workspace_id,
        "workspace": workspace.to_dict() if workspace else None,
        "committed": committed,
        "commit_errors": commit_errors,
        "build_brief_id": build_brief_id,
        "map_plan": map_plan,
        "map_preview": map_preview,
        "steps": steps,
        "plan": plan_for_confirm,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


__all__ = [
    "PIPELINE_STEP_ORDER",
    "STEP_LABELS",
    "run_narrative_pipeline",
]
