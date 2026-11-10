"""審核 API 業務邏輯。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.local_video_studio.models import Asset, Project, Review, Shot
from backend.local_video_studio.schemas import ReviewCreate, ReviewOut, ReviewQueueItem


def review_to_out(row: Review) -> ReviewOut:
    return ReviewOut(
        id=row.id,
        asset_id=row.asset_id,
        decision=row.decision,
        reason=row.reason,
        reviewer=row.reviewer,
        created_at=row.created_at,
    )


def create_review(session: Session, asset_id: str, body: ReviewCreate) -> ReviewOut:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="資產不存在")
    if body.decision not in {"approve", "reject", "needs_retry"}:
        raise HTTPException(status_code=422, detail="decision 無效")
    row = Review(
        asset_id=asset_id,
        decision=body.decision,
        reason=body.reason,
        reviewer=body.reviewer or "owner",
    )
    session.add(row)

    if asset.shot_id:
        shot = session.get(Shot, asset.shot_id)
        if shot is not None:
            if body.decision == "approve":
                shot.status = "approved"
                if asset.type in {"refine", "draft"}:
                    shot.selected_clip_asset_id = asset.id
            elif body.decision == "reject":
                shot.status = "rejected"
            else:
                shot.status = "refine_ready" if asset.type == "refine" else "draft_ready"

    session.flush()
    return review_to_out(row)


def review_queue(session: Session, project_id: str) -> list[ReviewQueueItem]:
    if session.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="專案不存在")
    assets = session.scalars(
        select(Asset)
        .where(Asset.project_id == project_id, Asset.type.in_(("draft", "refine", "final")))
        .order_by(Asset.created_at.desc())
    ).all()
    out: list[ReviewQueueItem] = []
    for asset in assets:
        latest = session.scalar(
            select(Review).where(Review.asset_id == asset.id).order_by(Review.created_at.desc())
        )
        if latest is not None and latest.decision == "approve":
            continue
        shot = session.get(Shot, asset.shot_id) if asset.shot_id else None
        out.append(
            ReviewQueueItem(
                asset_id=asset.id,
                project_id=asset.project_id,
                shot_id=asset.shot_id,
                asset_type=asset.type,
                relative_path=asset.relative_path,
                shot_status=shot.status if shot else None,
                last_decision=latest.decision if latest else None,
            )
        )
    return out
