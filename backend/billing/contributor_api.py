"""貢獻者 API — Key 綁定、收益、鎖倉／轉換（Phase 2 共享池）。"""
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
from backend.billing.shared_pool import evaluate_key_health

router = APIRouter(prefix="/billing/contributor", tags=["billing-contributor"])


class BindKeyRequest(BaseModel):
    encrypted_key: str = Field(min_length=8)
    vendor_id: str = "self_host"
    models: list[str] = Field(default_factory=list)
    daily_token_cap: int = Field(default=0, ge=0)
    concurrency: int = Field(default=1, ge=1, le=100)
    min_price: float = Field(default=0.0, ge=0)
    active_hours: list[int] = Field(default_factory=lambda: [0, 23])
    tos_class: str = Field(default="self_host", description="self_host 或 resale_allowed")
    org_id: str = ""


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
    if body.tos_class not in {"self_host", "resale_allowed"} and body.vendor_id != "self_host":
        raise HTTPException(422, "僅允許 self_host 或 resale_allowed 廠商 Key（ToS 紅線）")
    limits = {
        "vendor_id": body.vendor_id,
        "models": body.models,
        "daily_token_cap": body.daily_token_cap,
        "concurrency": body.concurrency,
        "min_price": body.min_price,
        "active_hours": body.active_hours,
        "tos_class": body.tos_class,
    }
    org_id = body.org_id.strip() or None
    return get_pool_store().bind_contributor_key(
        user_id,
        body.encrypted_key,
        limits,
        org_id=org_id,
        plaintext_key=body.encrypted_key,
    )


@router.get("/keys")
def list_contributor_keys(request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    keys = get_pool_store().list_contributor_keys_with_health(user_id)
    return {"items": keys, "count": len(keys)}


@router.get("/keys/{key_id}/health")
def contributor_key_health(key_id: str, request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    keys = get_pool_store().list_contributor_keys_with_health(user_id)
    owned = {k["key_id"] for k in keys}
    if key_id not in owned:
        raise HTTPException(404, "Key 不存在或不屬於此帳號")
    return evaluate_key_health(key_id)


@router.post("/keys/{key_id}/health-check")
def run_contributor_key_health_check(key_id: str, request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    keys = get_pool_store().list_contributor_keys_with_health(user_id)
    owned = {k["key_id"] for k in keys}
    if key_id not in owned:
        raise HTTPException(404, "Key 不存在或不屬於此帳號")
    return evaluate_key_health(key_id)


@router.get("/earnings")
def contributor_earnings(request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    earnings = get_pool_store().contributor_earnings(user_id)
    status = contribution_status(user_id)
    keys = get_pool_store().list_contributor_keys_with_health(user_id)
    return {**earnings, "keys_detail": keys, "contribution": status}


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
