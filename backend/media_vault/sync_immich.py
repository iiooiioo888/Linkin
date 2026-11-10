"""Immich 同步介面（stub；需 IMMICH_BASE_URL + IMMICH_API_KEY 才啟用）。"""

from __future__ import annotations

import os
from typing import Any


def immich_enabled() -> bool:
    return bool(os.environ.get("IMMICH_BASE_URL", "").strip() and os.environ.get("IMMICH_API_KEY", "").strip())


def sync_post_to_immich(post_id: str) -> dict[str, Any]:
    if not immich_enabled():
        return {"ok": False, "skipped": True, "reason": "Immich 未設定"}
    # 預留：httpx 上傳至 Immich REST
    return {"ok": False, "skipped": True, "reason": "stub", "post_id": post_id}
