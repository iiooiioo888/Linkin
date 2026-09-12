"""靈境積分計費 HTTP API。"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.auth.gate import gate_enabled
from backend.billing.context import current_billing_user, default_anonymous_user
from backend.billing.credits import public_rate_card
from backend.billing.enterprise import enterprise_status
from backend.billing.plans import is_public_plan_id, list_plans_public, normalize_plan_id
from backend.billing.quota import get_billing_service

router = APIRouter(prefix="/billing", tags=["billing"])
# 向後相容
wallet_router = APIRouter(prefix="/wallet", tags=["wallet"])


class TopupRequest(BaseModel):
    credits: float = Field(gt=0, description="充值靈境積分")
    reference: str = ""
    note: str = ""


class AssignPlanRequest(BaseModel):
    plan_id: str = Field(description="free / starter / pro / business / enterprise")


class AppealRequest(BaseModel):
    task_id: str = ""
    reason: str = Field(min_length=1)
    detail: str = ""
    appeal_kind: str = "general"
    installment_id: str = ""


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
    from backend.billing.contribution_service import contribution_status
    from backend.billing.docker_meter import get_docker_billing_tracker
    from backend.billing.pool_store import get_pool_store

    user_id = _resolve_user(request)
    svc = get_billing_service()
    account = svc.get_account(user_id)
    pools = get_pool_store().pools_detail(user_id, account.get("plan_id", "free"))
    contribution = contribution_status(user_id)
    docker = get_docker_billing_tracker().summary(user_id=user_id)
    docker_charges = [
        e for e in svc.usage_events(user_id, limit=100) if e.get("event_type") in {"docker_runtime", "docker"}
    ]
    docker_credits_spent = round(sum(float(e.get("credits") or 0) for e in docker_charges), 4)
    return {
        "account": account,
        "pools": pools,
        "contribution": contribution,
        "plans": list_plans_public(),
        "rate_card": public_rate_card(),
        "enterprise": enterprise_status(),
        "vendor_preference": get_pool_store().active_vendor_config(),
        "docker": {
            **docker,
            "recent_docker_events": docker_charges[:15],
            "total_docker_credits_spent": docker_credits_spent,
        },
    }


@router.get("")
def get_billing(request: Request) -> dict[str, Any]:
    return _account_payload(request)


@router.get("/overview")
def billing_overview(request: Request) -> dict[str, Any]:
    """帳務總覽聚合：本月消耗、餘額、異常 Key 數。"""
    from backend.billing.pool_store import get_pool_store

    user_id = _resolve_user(request)
    svc = get_billing_service()
    account = svc.get_account(user_id)
    keys = get_pool_store().list_contributor_keys_with_health(user_id)
    bad_statuses = {"unhealthy", "degraded", "offline"}
    unhealthy = [k for k in keys if str(k.get("health_status") or "") in bad_statuses]
    return {
        "user_id": user_id,
        "period_key": account.get("period_key"),
        "monthly_used_credits": float(account.get("monthly_used_credits") or 0),
        "balance_credits": float(account.get("balance_credits") or 0),
        "low_balance": bool(account.get("low_balance")),
        "unhealthy_keys_count": len(unhealthy),
        "unhealthy_keys": [
            {
                "key_id": k.get("key_id") or k.get("id"),
                "status": k.get("health_status"),
                "health_score": k.get("health_score"),
            }
            for k in unhealthy[:20]
        ],
    }


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
    plan_id = normalize_plan_id(req.plan_id)
    if req.plan_id.strip().lower() == "team":
        plan_id = "business"
    if not is_public_plan_id(plan_id):
        raise HTTPException(
            status_code=400,
            detail="無效方案，請選擇 free / starter / pro / business / enterprise",
        )
    user_id = _resolve_user(request)
    account = get_billing_service().set_plan(user_id, plan_id)
    return {"account": account}


@router.post("/appeals")
def submit_appeal(req: AppealRequest, request: Request) -> dict[str, Any]:
    from backend.billing.appeals import create_appeal

    user_id = _resolve_user(request)
    try:
        return create_appeal(
            user_id,
            task_id=req.task_id or None,
            reason=req.reason,
            detail=req.detail,
            appeal_kind=req.appeal_kind,
            installment_id=req.installment_id or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/appeals")
def list_my_appeals(request: Request, limit: int = 20) -> dict[str, Any]:
    from backend.billing.appeals import list_appeals

    user_id = _resolve_user(request)
    return {"appeals": list_appeals(user_id, limit=limit)}


@router.get("/pools")
def get_pools(request: Request) -> dict[str, Any]:
    from backend.billing.pool_store import get_pool_store

    user_id = _resolve_user(request)
    acct = get_billing_service().get_account(user_id)
    return get_pool_store().pools_detail(user_id, acct.get("plan_id", "free"))


@router.get("/rollover-records")
def my_rollover_records(request: Request, limit: int = 20) -> dict[str, Any]:
    from backend.billing.pool_store import get_pool_store

    user_id = _resolve_user(request)
    return {"items": get_pool_store().list_rollover_for_account(user_id, limit)}


@router.get("/grants")
def my_grants(request: Request, limit: int = 50) -> dict[str, Any]:
    from backend.billing.pool_store import get_pool_store

    user_id = _resolve_user(request)
    return {"items": get_pool_store().list_grants(user_id, limit)}


@router.get("/pools/ledger")
def my_pool_ledger(request: Request, limit: int = 50) -> dict[str, Any]:
    from backend.billing.pool_store import get_pool_store

    user_id = _resolve_user(request)
    return {"items": get_pool_store().list_pool_ledger(user_id, limit)}


@router.post("/contribution/convert")
def convert_contribution(request: Request, amount: float) -> dict[str, Any]:
    from backend.billing.contribution_service import convert_unlocked_to_purchased

    user_id = _resolve_user(request)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="轉換數量須大於 0")
    return convert_unlocked_to_purchased(user_id, amount)


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


@router.get("/token-dashboard", response_class=HTMLResponse)
def get_token_dashboard(request: Request, days: int = 90) -> HTMLResponse:
    """生成並返回 Token 用量看板 HTML（資料來自 Linkin 計費庫）。"""
    from backend.billing.token_dashboard.service import generate_token_dashboard_html

    user_id = _resolve_user(request)
    days = max(1, min(int(days), 365))
    html = generate_token_dashboard_html(user_id, days=days)
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.post("/token-dashboard/generate")
def post_token_dashboard(request: Request, days: int = 90) -> dict[str, Any]:
    """生成 Token 看板並返回統計摘要與 HTML。"""
    from backend.billing.token_dashboard.service import generate_token_dashboard_payload

    user_id = _resolve_user(request)
    days = max(1, min(int(days), 365))
    payload = generate_token_dashboard_payload(user_id, days=days)
    return {
        "user_id": user_id,
        "days": days,
        "stats": payload["stats"],
        "dashboard_url": "/billing/token-dashboard",
        "html": payload["html"],
    }


@router.post("/transfer")
def transfer_forbidden() -> dict[str, Any]:
    from backend.billing.pools_service import TransferForbiddenError

    raise HTTPException(status_code=403, detail=str(TransferForbiddenError()))


def register_billing(app) -> None:
    from backend.billing.admin_api import router as admin_router
    from backend.billing.contributor_api import router as contributor_router

    app.include_router(router)
    app.include_router(wallet_router)
    app.include_router(admin_router)
    app.include_router(contributor_router)
