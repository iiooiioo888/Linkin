"""MediaCrawler HTTP API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.mediacrawler.service import (
    get_job_detail,
    get_job_results,
    get_status,
    resolve_download_path,
    start_job,
    update_runtime_config,
    validate_job,
)

router = APIRouter(prefix="/mediacrawler", tags=["mediacrawler"])


class RuntimeConfigRequest(BaseModel):
    cookie: str = Field(default="", description="平台 Cookie（不寫入 Git）")


class CrawlJobBody(BaseModel):
    platform: str
    crawl_type: str = "search"
    login_type: str = "cookie"
    keywords: str = ""
    post_ids: str = ""
    creator_ids: str = ""
    enable_comments: bool = False
    save_format: str = "json"
    max_notes: int = Field(default=20, ge=1, le=500)
    dry_run: bool = False
    cookie: str = ""


@router.get("/status")
def mediacrawler_status() -> dict[str, Any]:
    return get_status()


@router.get("/config")
def mediacrawler_get_config() -> dict[str, Any]:
    return get_status()


@router.put("/config")
def mediacrawler_put_config(body: RuntimeConfigRequest) -> dict[str, Any]:
    return update_runtime_config(cookie=body.cookie)


@router.post("/jobs/validate")
def mediacrawler_validate_job(body: CrawlJobBody) -> dict[str, Any]:
    return validate_job(body.model_dump())


@router.post("/jobs")
def mediacrawler_create_job(body: CrawlJobBody) -> dict[str, Any]:
    try:
        return start_job(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs")
def mediacrawler_list_jobs(limit: int = 50) -> dict[str, Any]:
    from backend.mediacrawler.jobs import get_job_manager

    return {"jobs": get_job_manager().list_jobs(limit=limit)}


@router.get("/jobs/{job_id}")
def mediacrawler_get_job(job_id: str) -> dict[str, Any]:
    detail = get_job_detail(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return detail


@router.get("/jobs/{job_id}/results")
def mediacrawler_job_results(job_id: str) -> dict[str, Any]:
    detail = get_job_detail(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return {"job_id": job_id, "results": get_job_results(job_id)}


@router.get("/jobs/{job_id}/results/{filename}")
def mediacrawler_download_result(job_id: str, filename: str) -> FileResponse:
    try:
        path = resolve_download_path(job_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="檔案不存在")
    return FileResponse(path, filename=path.name)


def register_mediacrawler(app) -> None:
    app.include_router(router)
