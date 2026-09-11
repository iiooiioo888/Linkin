"""靈境積分計費 HTTP API。"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth.gate import gate_enabled
from backend.billing.context import current_billing_user, default_anonymous_user
from backend.billing.credits import public_rate_card
from backend.billing.enterprise import enterprise_status
from backend.billing.plans import list_plans_public
from backend.billing.quota import get_billing_service

router = APIRouter(prefix="/billing", tags=["billing"])
# 向後相容
wallet_router = APIRouter(prefix="/wallet", tags=["wallet"])


class TopupRequest(BaseModel):
    credits: float = Field(gt=0, description="充值靈境積分")
    reference: str = ""
    note: str = ""


class AssignPlanRequest(BaseModel):
    plan_id: str = Field(description="free / pro / team / enterprise")


def _resolve_user(request: Request) -> str:
    user = getattr(request.state, "gate_user", None) or current_billing_user()
    if user:
        return str(user).strip()
    if not gate_enabled():
        return default_anonymous_user()
    raise HTTPException(status_code=401, detail="未登入，無法查詢帳務")


def _admin_allowed(request: Request) -> bool:
    secret = os.getenv("LINKIN_BILLING_ADMIN_SECRET", "").strip() or os.getenv("LINKIN_WALLET_ADMIN_SECRET", "").strip()
    if secret:
        return (request.headers.get("X-Billing-Admin") or request.headers.get("X-Wallet-Admin") or "").strip() == secret
    return bool(getattr(request.state, "gate_user", None))


def _account_payload(request: Request) -> dict[str, Any]:
    user_id = _resolve_user(request)
    svc = get_billing_service()
    account = svc.get_account(user_id)
    return {
        "account": account,
        "plans": list_plans_public(),
        "rate_card": public_rate_card(),
        "enterprise": enterprise_status(),
    }


@router.get("")
def get_billing(request: Request) -> dict[str, Any]:
    return _account_payload(request)


@router.get("/usage")
def get_usage(request: Request, limit: int = 50) -> dict[str, Any]:
    user_id = _resolve_user(request)
    return {"user_id": user_id, "events": get_billing_service().usage_events(user_id, limit)}


@router.get("/ledger")
def get_ledger(request: Request, limit: int = 50) -> dict[str, Any]:
    user_id = _resolve_user(request)
    return {"user_id": user_id, "entries": get_billing_service().ledger(user_id, limit)}


@router.post("/topup")
def topup(req: TopupRequest, request: Request) -> dict[str, Any]:
    if not _admin_allowed(request):
        raise HTTPException(status_code=403, detail="無權限執行充值")
    user_id = _resolve_user(request)
    return get_billing_service().topup_credits(
        user_id, req.credits, reference=req.reference or "api_topup", meta={"note": req.note} if req.note else None
    )


@router.post("/assign-plan")
def assign_plan(req: AssignPlanRequest, request: Request) -> dict[str, Any]:
    if not _admin_allowed(request):
        raise HTTPException(status_code=403, detail="無權限指派方案")
    user_id = _resolve_user(request)
    account = get_billing_service().set_plan(user_id, req.plan_id)
    return {"account": account}


@wallet_router.get("")
def wallet_alias(request: Request) -> dict[str, Any]:
    payload = _account_payload(request)
    acct = payload["account"]
    return {
        "account": {
            **acct,
            "balance_usd": acct["balance_credits"] / 1000.0,
            "currency": "Linkin Credit",
        },
        "pricing": payload["rate_card"],
    }


@wallet_router.get("/ledger")
def wallet_ledger_alias(request: Request, limit: int = 50) -> dict[str, Any]:
    return get_ledger(request, limit)


@wallet_router.post("/topup")
def wallet_topup_alias(req: TopupRequest, request: Request) -> dict[str, Any]:
    return topup(req, request)


def register_billing(app) -> None:
    app.include_router(router)
    app.include_router(wallet_router)
