"""合規標識：成片成功前必須 stamp。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.local_video_studio.config import load_config
from backend.local_video_studio.models import Asset, ComplianceRecord


class ComplianceError(RuntimeError):
    pass


def stamp(
    session: Session,
    *,
    asset: Asset,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
) -> ComplianceRecord:
    """寫入 ComplianceRecord；compose 成功路徑必呼叫。"""
    cfg = load_config()
    meta = {
        "ai_generated": True,
        "ai_service": "local-video-studio",
        "ai_model": "wan2.2-5b;ltx-video;flux-ipadapter",
        "explicit_text": cfg.compliance_text,
        "explicit_position": cfg.compliance_position,
        "created_at": datetime.now(UTC).isoformat(),
        **(metadata or {}),
    }
    if not meta.get("ai_generated"):
        raise ComplianceError("ai_generated 必須為 true")
    existing = session.scalar(
        select(ComplianceRecord).where(ComplianceRecord.asset_id == asset.id)
    )
    if existing is not None and not force:
        return existing
    record = ComplianceRecord(
        asset_id=asset.id,
        explicit_mark=True,
        metadata_json=meta,
        watermark_id=f"lvs-{asset.id[:8]}",
    )
    session.add(record)
    session.flush()
    return record


def require_stamped(session: Session, asset_id: str) -> ComplianceRecord:
    rec = session.scalar(select(ComplianceRecord).where(ComplianceRecord.asset_id == asset_id))
    if rec is None:
        raise ComplianceError("缺少 ComplianceRecord；禁止略過 stamp")
    return rec
