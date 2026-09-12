"""Phase 2 REST：build_brief 預覽與落地建築（需使用者明確觸發 apply）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.linkin.build_brief_apply import (
    BuildBriefError,
    apply_build_brief,
    cancel_job,
    get_build_brief,
    get_job,
    job_to_dict,
    list_build_briefs,
    preview_build_brief,
    start_apply_job,
    validate_build_brief,
)

build_brief_router = APIRouter(prefix="/linkin/build-briefs", tags=["linkin-build-briefs"])


def _brief_http(exc: BuildBriefError) -> HTTPException:
    status = 404 if exc.code == "not_found" else 409 if exc.code in {"bridge_offline", "bridge_disabled"} else 400
    return HTTPException(status_code=status, detail={"message": str(exc), "code": exc.code, **exc.extra})


def _resolve_brief(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("brief") and isinstance(body["brief"], dict):
        return validate_build_brief(body["brief"])
    brief_id = str(body.get("brief_id") or body.get("id") or "").strip()
    if brief_id:
        return validate_build_brief(get_build_brief(brief_id))
    raise BuildBriefError("需要 brief_id 或 brief payload", code="missing_brief")


@build_brief_router.get("")
def api_list_build_briefs() -> dict[str, Any]:
    items = list_build_briefs()
    return {"build_briefs": items, "count": len(items)}


@build_brief_router.get("/{brief_id}")
def api_get_build_brief(brief_id: str) -> dict[str, Any]:
    try:
        brief = get_build_brief(brief_id)
    except BuildBriefError as exc:
        raise _brief_http(exc) from exc
    return {"build_brief": brief}


@build_brief_router.post("/preview")
def api_preview_build_brief_body(body: dict[str, Any]) -> dict[str, Any]:
    try:
        brief = _resolve_brief(body)
        generate = bool(body.get("generate", True))
        return preview_build_brief(brief, generate=generate)
    except BuildBriefError as exc:
        raise _brief_http(exc) from exc


@build_brief_router.post("/{brief_id}/preview")
def api_preview_build_brief_id(brief_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(body or {})
    payload.setdefault("brief_id", brief_id)
    return api_preview_build_brief_body(payload)


@build_brief_router.post("/apply")
def api_apply_build_brief_body(body: dict[str, Any]) -> dict[str, Any]:
    if not body.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail={"message": "落地建築需 confirm=true 明確確認", "code": "confirm_required"},
        )
    try:
        brief = _resolve_brief(body)
    except BuildBriefError as exc:
        raise _brief_http(exc) from exc

    dry_run = bool(body.get("dry_run"))
    async_mode = bool(body.get("async"))

    if async_mode:
        job = start_apply_job(brief, dry_run=dry_run)
        return {"job": job_to_dict(job)}

    try:
        return apply_build_brief(brief, dry_run=dry_run)
    except BuildBriefError as exc:
        raise _brief_http(exc) from exc


@build_brief_router.post("/{brief_id}/apply")
def api_apply_build_brief_id(brief_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(body or {})
    payload.setdefault("brief_id", brief_id)
    return api_apply_build_brief_body(payload)


@build_brief_router.get("/jobs/{job_id}")
def api_get_build_job(job_id: str) -> dict[str, Any]:
    try:
        return {"job": job_to_dict(get_job(job_id))}
    except BuildBriefError as exc:
        raise _brief_http(exc) from exc


@build_brief_router.post("/jobs/{job_id}/cancel")
def api_cancel_build_job(job_id: str) -> dict[str, Any]:
    try:
        job = cancel_job(job_id)
        return {"job": job_to_dict(job)}
    except BuildBriefError as exc:
        raise _brief_http(exc) from exc
