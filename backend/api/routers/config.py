"""LLM 配置、多路由、反饋與監控快照 API（自 backend.main 抽出）。"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.api_router import (
    delete_route,
    public_router_state,
    save_routes,
    set_route_strategy,
    upsert_route,
)
from backend.core.llm import call_llm
from backend.core.llm_config import (
    get_runtime_config,
    masked_key,
    merge_runtime_config,
    save_runtime_config,
)
from backend.core.provider_pool import (
    public_pool,
    refresh_model_catalog,
    refresh_route_catalog,
    set_refresh_interval,
)
from backend.services.llm_ops import collect_llm_ops, run_ops_once
from backend.services.optimization_monitor import collect_optimization_monitor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["config"])


class LlmConfigRequest(BaseModel):
    api_key: str | None = None
    api_base: str | None = None
    model: str | None = None
    route_strategy: str | None = None
    default_route_id: str | None = None


class ApiRouteBody(BaseModel):
    id: str = ""
    name: str = ""
    provider: str = ""
    api_key: str | None = None
    api_base: str = ""
    model: str = ""
    models: list[str] = []
    allowed_models: list[str] = []
    weight: int = 10
    enabled: bool = True
    fallback: bool = False
    is_default: bool = False
    models_locked: bool = False
    keep_api_key: bool = False
    provider_routing: dict[str, Any] | None = None


class ApiRoutesReplaceBody(BaseModel):
    api_routes: list[ApiRouteBody]
    route_strategy: str | None = None
    default_route_id: str = ""


class RouteStrategyBody(BaseModel):
    route_strategy: str
    default_route_id: str | None = None


class LlmOpsPrefsBody(BaseModel):
    refresh_interval_sec: int


class FeedbackRequest(BaseModel):
    session_id: str
    signal: str  # thumbs_up | thumbs_down | copy | edit
    score: float | None = None
    query_length: int = 0
    comment: str = ""


@router.get("/config")
async def get_config():
    """回傳当前 LLM 配置（金鑰脱敏）與可用模型池。只含目前登入帳號。"""
    from backend.core.user_settings import active_settings_user

    cfg = get_runtime_config()
    pool = public_pool(cfg)
    uid = active_settings_user() or ""
    return {
        "configured": bool(cfg.get("api_key")),
        "api_key": masked_key(cfg.get("api_key", "")),
        "api_base": cfg.get("api_base", ""),
        "model": cfg.get("model", "") or pool.get("model", ""),
        **pool,
        "settings_user": uid,
        "settings_isolated": bool(uid),
    }


@router.post("/config")
async def update_config(req: LlmConfigRequest):
    """動態更新目前帳號的 LLM 配置（即時生效並持久化），隨後刷新可用模型池。"""
    from backend.core.user_settings import guard_settings_write

    guard_settings_write()
    save_runtime_config(api_key=req.api_key, api_base=req.api_base, model=req.model)
    if req.route_strategy:
        set_route_strategy(req.route_strategy)
    if req.default_route_id:
        merge_runtime_config({"default_route_id": req.default_route_id.strip().lower()})
    logger.info("LLM 配置已更新（model=%s, api_base=%s）", req.model, req.api_base)
    try:
        refresh_model_catalog(reason="save")
    except Exception as exc:
        logger.warning("儲存後刷新模型目錄失敗：%s", exc)
    return await get_config()


@router.get("/config/routes")
async def get_config_routes():
    """多 API 路由清單（金鑰脱敏）。"""
    return public_router_state()


@router.put("/config/routes")
async def replace_config_routes(body: ApiRoutesReplaceBody):
    """整批覆寫目前帳號的 API 路由。"""
    from backend.core.user_settings import guard_settings_write

    guard_settings_write()
    save_routes(
        [r.model_dump() for r in body.api_routes],
        strategy=body.route_strategy,
        default_id=body.default_route_id,
    )
    try:
        refresh_model_catalog(reason="routes")
    except Exception as exc:
        logger.warning("路由儲存後刷新目錄失敗：%s", exc)
    return public_router_state()


@router.post("/config/routes")
async def upsert_config_route(body: ApiRouteBody):
    """新增或更新目前帳號的一條 API 路由。"""
    from backend.core.user_settings import guard_settings_write

    guard_settings_write()
    route = upsert_route(body.model_dump())
    try:
        refresh_route_catalog(route["id"], reason="save")
    except Exception as exc:
        logger.warning("路由 %s 刷新目錄失敗：%s", route.get("id"), exc)
    return public_router_state()


@router.delete("/config/routes/{route_id}")
async def delete_config_route(route_id: str):
    from backend.core.user_settings import guard_settings_write

    guard_settings_write()
    delete_route(route_id)
    return public_router_state()


@router.post("/config/routes/{route_id}/refresh")
async def refresh_config_route(route_id: str):
    try:
        return await asyncio.to_thread(refresh_route_catalog, route_id, reason="manual")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"刷新路由目錄失敗：{exc}") from exc


@router.post("/config/routes/{route_id}/test")
async def test_config_route(route_id: str):
    """以指定路由實際呼叫 LLM 驗證連線。"""
    try:
        reply = await asyncio.to_thread(call_llm, "請用兩個字回覆：成功。", temperature=0, route_id=route_id)
        return {"ok": True, "reply": reply.strip(), "route_id": route_id}
    except Exception as exc:
        logger.warning("路由 %s 連線測試失敗：%s", route_id, exc)
        return {"ok": False, "error": str(exc)[:300], "route_id": route_id}


@router.put("/config/strategy")
async def update_route_strategy(body: RouteStrategyBody):
    from backend.core.user_settings import guard_settings_write

    guard_settings_write()
    strategy = set_route_strategy(body.route_strategy)
    if body.default_route_id:
        merge_runtime_config({"default_route_id": body.default_route_id.strip().lower()})
    state = public_router_state()
    state["route_strategy"] = strategy
    return state


@router.post("/config/models/refresh")
async def refresh_config_models():
    """立刻爬取通用端點 /models 或重建單一廠商靜態池。"""
    try:
        return await asyncio.to_thread(run_ops_once, "manual")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"刷新模型目錄失敗：{exc}") from exc


@router.post("/config/cost-speed/reload")
async def reload_cost_speed_config():
    """熱重載 cost_speed 路由配置（修改 JSON 後無需重啟）。"""
    from backend.core.cost_speed_router import reload_cost_speed

    return await asyncio.to_thread(reload_cost_speed)


@router.put("/config/ops")
async def update_llm_ops(body: LlmOpsPrefsBody):
    """更新目前帳號的模型目錄定時檢查間隔（秒）。"""
    from backend.core.user_settings import guard_settings_write

    guard_settings_write()
    return set_refresh_interval(body.refresh_interval_sec)


@router.get("/monitor/llm-ops")
async def monitor_llm_ops():
    """監控中心：目前 API 鎖定的模型池與定時檢查狀態。"""
    return collect_llm_ops()


@router.get("/monitor/optimization")
async def monitor_optimization():
    """監控中心：P0–P3 性能優化路線圖運行時指標。"""
    return collect_optimization_monitor()


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    """收集用戶顯式/隱式反饋，供反思策略自適應調整。"""
    from backend.core.user_feedback import record_feedback

    allowed = {"thumbs_up", "thumbs_down", "copy", "edit"}
    if body.signal not in allowed:
        return {"ok": False, "error": f"signal 必須為 {allowed}"}
    entry = record_feedback(
        session_id=body.session_id,
        signal=body.signal,  # type: ignore[arg-type]
        score=body.score,
        query_length=body.query_length,
        comment=body.comment,
    )
    return {"ok": True, "record": entry}


@router.get("/feedback/stats")
async def feedback_stats():
    """用戶反饋統計摘要。"""
    from backend.core.user_feedback import feedback_stats as _stats

    return _stats()


@router.get("/monitor/hub-snapshot")
async def monitor_hub_snapshot():
    """監控中心彙總快照（REST 降級用，與 /monitor/ws 同結構）。"""
    from backend.services.monitor_hub import collect_monitor_hub

    return await asyncio.to_thread(collect_monitor_hub)


@router.post("/config/test")
async def test_config():
    """以当前配置實際呼叫 LLM 驗證連線。"""
    try:
        reply = await asyncio.to_thread(call_llm, "請用兩個字回覆：成功。", temperature=0)
        return {"ok": True, "reply": reply.strip()}
    except Exception as exc:
        logger.warning("LLM 連線測試失敗：%s", exc)
        return {"ok": False, "error": str(exc)[:300]}
