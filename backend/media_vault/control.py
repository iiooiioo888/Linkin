"""控制面板聚合（MediaCrawler + Vault 計數）。"""

from __future__ import annotations

from typing import Any

from backend.media_vault.monitor import monitor_summary


def control_overview() -> dict[str, Any]:
    vault = monitor_summary()
    mc: dict[str, Any]
    try:
        from backend.mediacrawler.service import get_status

        mc = get_status()
    except Exception as exc:
        mc = {"ok": False, "error": str(exc)}
    return {
        "vault": {
            "today_ingested": vault.get("today_ingested", 0),
            "total_posts": vault.get("total_posts", 0),
            "success_rate": vault.get("success_rate"),
            "media_root": vault.get("media_root"),
        },
        "mediacrawler": mc,
    }
