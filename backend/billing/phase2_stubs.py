"""Phase 2+ 共享池／fault_pool／貢獻者 API 樁（不阻塞 MVP）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/billing/contributor", tags=["billing-contributor-stub"])


class BindKeyRequest(BaseModel):
    encrypted_key: str
    org_id: str | None = None


@router.post("/bind-key")
def bind_contributor_key(_body: BindKeyRequest) -> dict:
    raise HTTPException(501, "Phase 2：貢獻者 Key 綁定尚未啟用")


@router.get("/earnings")
def contributor_earnings() -> dict:
    return {"phase": "stub", "earnings": 0, "locked_contribution": 0}


@router.post("/redeem")
def contributor_redeem() -> dict:
    raise HTTPException(501, "Phase 2：貢獻積分解鎖尚未啟用")
