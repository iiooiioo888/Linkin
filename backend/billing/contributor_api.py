"""貢獻者 API — Key 綁定、收益、鎖倉／轉換。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.billing.api import _resolve_user
from backend.billing.contribution_service import (
    contribution_status,
    convert_unlocked_to_purchased,
    early_unlock_contribution,
    lock_contribution,
    process_due_installments,
)
from backend.billing.pool_store import get_pool_store

router = APIRouter(prefix="/billing/contributor", tags=["billing-contributor"])


class BindKeyRequest(BaseModel):
    encrypted_key: str = Field(min_length=8)
    vendor_id: str = "self_host"
    models: list[str] = Field(default_factory=list)


class LockRequest(BaseModel):
    amount: float = Field(gt=0)
    lock_days: int = Field(description="30 / 90 / 180")


class ConvertRequest(BaseModel):
    amount: float = Field(gt=0)


class EarlyUnlockRequest(BaseModel):
    installment_id: str = Field(min_length=4)


@router.post("/bind-key")
def bind_contributor_key(body: BindKeyRequest, request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    limits = {"vendor_id": body.vendor_id, "models": body.models}
    return get_pool_store().bind_contributor_key(user_id, body.encrypted_key, limits)


@router.get("/earnings")
def contributor_earnings(request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    earnings = get_pool_store().contributor_earnings(user_id)
    status = contribution_status(user_id)
    return {**earnings, "contribution": status}


@router.get("/contribution/status")
def get_contribution_status(request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    return contribution_status(user_id)


@router.post("/contribution/lock")
def lock_contribution_endpoint(body: LockRequest, request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    try:
        return lock_contribution(user_id, body.amount, body.lock_days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/contribution/convert")
def convert_contribution(body: ConvertRequest, request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    return convert_unlocked_to_purchased(user_id, body.amount)


@router.post("/contribution/unlock-installments")
def trigger_installments(request: Request, force: bool = False) -> dict[str, Any]:
    user_id = _resolve_user(request)
    processed = process_due_installments(user_id, force=force)
    return {"processed": processed, "status": contribution_status(user_id)}


@router.post("/contribution/early-unlock")
def early_unlock_endpoint(body: EarlyUnlockRequest, request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    try:
        return early_unlock_contribution(user_id, body.installment_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
