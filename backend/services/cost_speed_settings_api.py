"""cost_speed 可寫設定 HTTP 面（post_company_reflect 等，供未來 UI 接入）。

寫入端點與 ``PUT /config/routes`` 等相同：受 ``AuthGateMiddleware`` 保護
（``LINKIN_AUTH_FORCE`` / 部署閘門開啟時須有效會話；無 per-route admin token）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.cost_speed_router import (
    post_company_reflect_config_value,
    routing_feedback_settings,
    update_cost_speed_config,
)
from backend.core.post_company_reflect import (
    post_company_reflect_mode,
    post_company_reflect_resolution,
)

router = APIRouter(prefix="/config/cost-speed", tags=["cost-speed-config"])


class PostCompanyReflectBody(BaseModel):
    mode: str = Field(..., description="off | evaluate | full")


@router.get("/post-company-reflect")
def get_post_company_reflect() -> dict[str, Any]:
    """讀取公司後反思模式：effective 為實際生效值，config 為 JSON 檔內容。"""
    resolution = post_company_reflect_resolution()
    return {
        "effective": post_company_reflect_mode(),
        "config": post_company_reflect_config_value(),
        "source": resolution.get("source"),
        "allowed": ["off", "evaluate", "full"],
    }


@router.put("/post-company-reflect")
def put_post_company_reflect(body: PostCompanyReflectBody) -> dict[str, Any]:
    """寫入 cost_speed.json 的 post_company_reflect（環境變數仍可覆蓋 effective）。"""
    try:
        update_cost_speed_config(post_company_reflect=body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_post_company_reflect()


@router.get("/routing-feedback")
def get_routing_feedback_config() -> dict[str, Any]:
    """讀取 routing_feedback 成本護欄配置（唯讀快照）。"""
    return {"routing_feedback": routing_feedback_settings()}


def register_cost_speed_settings(app: Any) -> None:
    app.include_router(router)
