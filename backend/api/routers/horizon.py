"""Horizon 公開資料掃描 API（自 backend.main 抽出）。

GET /horizon/latest、POST /horizon/scan、POST /horizon/proposals/{id}/decide、
POST /horizon/proposals/{id}/rollback。掃描只讀固定主題的公開倉庫；寫入參考筆記
前一定先停在 `awaiting_confirmation`，需人工點頭。
"""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["horizon"])


class HorizonDecision(BaseModel):
    action: str = ""
    note: str = ""


def _horizon_root():
    from backend.company.horizon import horizon_path

    return horizon_path().parent


@router.get("/horizon/latest")
async def horizon_latest():
    """上一份公開資料摘要。沒有掃過就回空。"""
    from backend.company.horizon import load_latest

    brief = load_latest()
    if not brief:
        return {"ok": False, "topics": [], "note": "尚未掃描"}
    return brief


@router.post("/horizon/scan")
async def horizon_scan():
    """依固定主題讀公開倉庫。不接受網址，不改程式。"""
    from backend.company.horizon import scan_horizon

    return await asyncio.to_thread(scan_horizon)


@router.post("/horizon/proposals/{proposal_id}/decide")
async def horizon_decide(proposal_id: str, body: HorizonDecision):
    """點頭才寫入參考筆記。凍結面不能通過。"""
    from backend.company.horizon_loop import decide_proposal

    ok, message = await asyncio.to_thread(
        decide_proposal, _horizon_root(), proposal_id, body.action.strip(), body.note
    )
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


@router.post("/horizon/proposals/{proposal_id}/rollback")
async def horizon_rollback(proposal_id: str):
    """撤銷已寫入的參考筆記。"""
    from backend.company.horizon_loop import rollback_proposal

    ok, message = await asyncio.to_thread(rollback_proposal, _horizon_root(), proposal_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}
