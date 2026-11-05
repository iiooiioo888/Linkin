"""media-collect 工具契約。reuse 走既有 MediaCrawler；缺口不抓取。"""

from __future__ import annotations

from typing import Any

from backend.mediacrawler.service import start_job

REUSE_TOOLS = {
    "search_douyin": "dy",
    "search_xhs": "xhs",
}

GAP_TOOLS = {
    "search_tiktok": "TikTok",
    "search_instagram": "Instagram",
    "search_x": "X",
}

_DOWNLOAD_PLATFORMS = {
    "dy": "dy",
    "douyin": "dy",
    "抖音": "dy",
    "xhs": "xhs",
    "xiaohongshu": "xhs",
    "小紅書": "xhs",
}


def dispatch_tool(payload: dict[str, Any]) -> dict[str, Any]:
    if _has_secret(payload):
        raise ValueError("此契約不接受 cookie、帳密或 session")
    tool = str(payload.get("tool") or "").strip()
    if tool in GAP_TOOLS:
        return {
            "tool": tool,
            "status": "gap",
            "platform": GAP_TOOLS[tool],
            "items": [],
            "detail": "尚無倉庫內工具，不抓取、不假造內容",
        }
    if tool in REUSE_TOOLS:
        return _search_reuse(tool, payload)
    if tool == "download_media":
        return _download_handoff(payload)
    raise ValueError(f"未知工具：{tool or '(empty)'}")


def _search_reuse(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    creator_id = str(payload.get("creator_id") or "").strip()
    if bool(query) == bool(creator_id):
        raise ValueError("search 需提供 query 或 creator_id 其中一個")
    limit = _limit(payload.get("limit"))
    body: dict[str, Any] = {
        "platform": REUSE_TOOLS[tool],
        "crawl_type": "creator" if creator_id else "search",
        "keywords": query,
        "creator_ids": creator_id,
        "max_notes": limit,
        "save_format": "json",
        "dry_run": bool(payload.get("dry_run", True)),
    }
    job = start_job(body)
    return {
        "tool": tool,
        "status": "submitted",
        "platform": REUSE_TOOLS[tool],
        "disposition": "reuse",
        "dry_run": body["dry_run"],
        "job": _public_job(job),
        "items": [],
        "persist": "media_vault.ingest",
    }


def _download_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    platform = _DOWNLOAD_PLATFORMS.get(str(payload.get("platform") or "").strip().lower())
    if platform is None:
        chinese = str(payload.get("platform") or "").strip()
        platform = _DOWNLOAD_PLATFORMS.get(chinese)
    source_url = str(payload.get("source_url") or "").strip()
    asset_url = str(payload.get("asset_url") or "").strip()
    if platform is None or not source_url or not asset_url:
        raise ValueError("download_media 需提供已支援平台、source_url、asset_url")
    return {
        "tool": "download_media",
        "status": "handoff",
        "platform": platform,
        "source_url": source_url,
        "asset_url": asset_url,
        "fetched": False,
        "persist": "media_vault.ingest",
        "detail": "不另開下載路徑；檔案由 MediaCrawler 任務結果經 Media Vault ingest 入庫",
    }


def _limit(raw: Any) -> int:
    try:
        value = int(raw if raw is not None else 20)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 須為整數") from exc
    return max(1, min(50, value))


def _has_secret(payload: dict[str, Any]) -> bool:
    for key in ("cookie", "password", "session", "token"):
        if str(payload.get(key) or "").strip():
            return True
    return False


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    request = job.get("request")
    if isinstance(request, dict):
        request = {k: v for k, v in request.items() if k != "cookie"}
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "dry_run": job.get("dry_run"),
        "request": request,
    }
