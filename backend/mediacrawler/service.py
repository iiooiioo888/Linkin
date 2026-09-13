"""MediaCrawler 高階服務入口。"""

from __future__ import annotations

from typing import Any

from backend.mediacrawler.config import (
    CrawlJobRequest,
    integration_status,
    load_env_config,
    set_stored_cookie,
)
from backend.mediacrawler.jobs import get_job_manager
from backend.mediacrawler.paths import list_result_files, safe_result_path


def get_status() -> dict[str, Any]:
    env = load_env_config()
    mgr = get_job_manager(env)
    status = integration_status(env)
    status["running_jobs"] = mgr.running_count()
    status["recent_jobs"] = mgr.list_jobs(limit=5)
    return status


def update_runtime_config(cookie: str | None = None) -> dict[str, Any]:
    if cookie is not None:
        set_stored_cookie(cookie)
    env = load_env_config()
    status = integration_status(env)
    return {
        "cookie_configured": status["cookie_configured"],
        "cookie_preview": status["cookie_preview"],
    }


def validate_job(payload: dict[str, Any]) -> dict[str, Any]:
    req = CrawlJobRequest(**_coerce_request(payload))
    return get_job_manager().validate(req)


def start_job(payload: dict[str, Any]) -> dict[str, Any]:
    req = CrawlJobRequest(**_coerce_request(payload))
    job = get_job_manager().submit(req)
    return job.to_dict()


def get_job_detail(job_id: str) -> dict[str, Any] | None:
    job = get_job_manager().get_job(job_id)
    if job is None:
        return None
    data = job.to_dict()
    data["log_tail"] = get_job_manager().tail_log(job_id)
    data["results"] = list_result_files(job_id)
    return data


def get_job_results(job_id: str) -> list[dict[str, str | int]]:
    return list_result_files(job_id)


def resolve_download_path(job_id: str, filename: str):
    return safe_result_path(job_id, filename)


def _coerce_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": str(payload.get("platform") or ""),
        "crawl_type": str(payload.get("crawl_type") or payload.get("type") or "search"),
        "login_type": str(payload.get("login_type") or payload.get("lt") or "cookie"),
        "keywords": str(payload.get("keywords") or ""),
        "post_ids": str(payload.get("post_ids") or ""),
        "creator_ids": str(payload.get("creator_ids") or ""),
        "enable_comments": bool(payload.get("enable_comments")),
        "save_format": str(payload.get("save_format") or "json"),
        "max_notes": int(payload.get("max_notes") or 20),
        "dry_run": bool(payload.get("dry_run")),
        "cookie": str(payload.get("cookie") or ""),
    }
