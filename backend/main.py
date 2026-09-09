"""EvoLoop 后端 FastAPI 入口。

启动方式：
    python -m backend.main
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

import logging
import time
from contextlib import asynccontextmanager
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncio
import json as json_mod

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.auth.gate import (
    AUTH_COOKIE,
    SESSION_TTL_SEC,
    clear_session,
    extract_token,
    issue_login,
    session_user,
    ws_authorized,
)
from backend.middleware.auth_gate import AuthGateMiddleware

from backend.core.graph import MAX_ITERATIONS, PASS_THRESHOLD, evoloop_graph
from backend.core import nodes
from backend.core.llm import call_llm, call_llm_stream, split_thinking
from backend.core.llm_config import get_runtime_config, masked_key, save_runtime_config
from backend.core.provider_pool import public_pool, refresh_model_catalog, refresh_route_catalog, set_refresh_interval
from backend.core.api_router import (
    delete_route,
    public_router_state,
    save_routes,
    set_route_strategy,
    upsert_route,
)
from backend.services.llm_ops import collect_llm_ops, llm_ops_loop, run_ops_once
from backend.hub.monitor import collect_hub_monitor
from backend.services.optimization_monitor import collect_optimization_monitor
from backend.company.role_catalog import (
    create_custom_role,
    delete_custom_role,
    reset_role_settings,
    update_monitor_prefs,
    update_role_settings,
)
from backend.services.agent_monitor import collect_agent_monitor
from backend.services.dashboard import collect_dashboard
from backend.services.opc_monitor import collect_opc_monitor
from backend.services.docker_manager import get_docker_manager
from backend.company.docker_tools import DOCKER_SERVICE_HOURLY_RATES
from backend.services.cloud_console import (
    get_cloud_alerts,
    get_cloud_billing,
    get_cloud_events,
    get_cloud_monitor,
)
from backend.services.task_broadcaster import task_broadcaster
from backend.services.task_manager import task_manager
from backend.services import lab_tools
from backend.hub.api import register_hub
from backend.linkin.api import register_linkin

# ═══════════════════════════════════════════════════════════════
# 全局公司預算狀態（由 orchestrator 更新，API 讀取）
# ═══════════════════════════════════════════════════════════════

_company_budget_state: dict[str, Any] = {
    "api_cost": 0.0,
    "docker_cost": 0.0,
    "aliyun_cost": 0.0,
    "cloud_cost": 0.0,
    "total_spent": 0.0,
    "budget_pressure": 0.0,
    "optimization_suggestions": [],
    "auto_optimized": {},
    "last_updated": "",
}


def update_company_budget_state(state: dict[str, Any]) -> None:
    """由公司 orchestrator 調用，更新全局預算狀態。"""
    global _company_budget_state
    _company_budget_state = {
        **state,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # 重啟回灌：從 Redis 載回任務記錄，修復任務列表／管線重啟後清空
    try:
        await asyncio.to_thread(task_manager.rehydrate)
    except Exception as exc:  # noqa: BLE001
        logger.warning("任務 rehydrate 失敗（降級為記憶體）：%s", exc)
    # 技能庫與 MCP：載入設定並把啟用 server 的工具掛進 tool_registry
    try:
        from backend.company.mcp_clients import mcp_registry
        from backend.company.skills import skills_store
        from backend.company.tools import tool_registry

        skills_store.load()
        mounted = await asyncio.to_thread(mcp_registry.mount_tools, tool_registry)
        if mounted:
            logger.info("啟動掛載 MCP 工具 %d 個", len(mounted))
    except Exception as exc:  # noqa: BLE001
        logger.warning("技能／MCP 啟動掛載失敗（降級為無）：%s", exc)
    task = asyncio.create_task(llm_ops_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="靈境·Linkin — Evoloop 運行時",
    description="靈境·Linkin 世界觀控制面 + EvoLoop 反思闭环 / 多代理人公司运行时",
    version="0.1.0",
    lifespan=_lifespan,
)

# CORS 配置：僅允許受信任的來源
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
if not allowed_origins:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
    ]

logger.info("CORS allowed origins: %s", allowed_origins)

app.add_middleware(AuthGateMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id", "X-Routing-Strategy", "X-Failover-Config", "CF-IPCountry", "X-Linkin-Gate"],
    expose_headers=["X-Request-Id", "X-Trace-Id", "X-Chosen-Provider", "X-Cost-Usd", "X-Latency-Ms", "X-Hub-Cache", "X-RateLimit-Remaining"],
    max_age=600,
)

# AI Hub 旁路面：/api/v1/*（Nginx 剝除 /api 時另掛 /v1/*）
register_hub(app)
register_linkin(app)


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    # 統一模式：執行策略（auto / simple / company），預設 auto 自動判斷
    execution_strategy: str = "auto"
    company_template: str = "quick_task"
    # 多輪對話歷史：[{"role": "user"|"assistant", "content": "..."}, ...]
    history: list[dict[str, str]] = []
    # RAHO：用戶 Grill-Me 鎖定後的戰役簡報
    semantic_lock: dict[str, Any] | None = None
    skip_user_grill: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    score: float | None = None
    iteration: int = 0
    status: str = "ok"
    grill: dict[str, Any] | None = None


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


class TaskRequest(BaseModel):
    query: str
    # 統一模式：執行策略（auto / simple / company），預設 auto 自動判斷
    execution_strategy: str = "auto"
    company_template: str = "quick_task"
    # 控制細項（進階參數）
    options: dict[str, Any] = {}


class FeedbackRequest(BaseModel):
    session_id: str
    signal: str  # thumbs_up | thumbs_down | copy | edit
    score: float | None = None
    query_length: int = 0
    comment: str = ""

@app.get("/health")
async def health():
    return {"status": "ok"}


class GateLoginBody(BaseModel):
    username: str = ""
    password: str = ""


def _client_identity(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "")


def _set_gate_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=SESSION_TTL_SEC,
        httponly=True,
        samesite="lax",
        path="/",
        secure=False,
    )


@app.post("/auth/login")
async def auth_login(body: GateLoginBody, request: Request):
    token = issue_login(body.username, body.password, identity=_client_identity(request))
    if not token:
        raise HTTPException(status_code=401, detail="帳號或密碼不正確")
    resp = JSONResponse({"ok": True, "user": body.username.strip(), "token": token})
    _set_gate_cookie(resp, token)
    return resp


@app.get("/auth/me")
async def auth_me(request: Request):
    token = extract_token(request.headers, request.cookies, request.query_params)
    user = session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="未登入或會話已失效")
    return {"ok": True, "user": user}


@app.post("/auth/logout")
async def auth_logout(request: Request):
    token = extract_token(request.headers, request.cookies, request.query_params)
    clear_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(AUTH_COOKIE, path="/")
    return resp


class RahoGrillStartBody(BaseModel):
    query: str
    execution_strategy: str = "auto"


class RahoGrillTurnBody(BaseModel):
    session_id: str
    answer: str = ""
    force_lock: bool = False


class RahoDecideBody(BaseModel):
    decision_id: str
    choice: str
    note: str = ""


class RahoCommanderPlanBody(BaseModel):
    ticket: dict[str, Any] | None = None
    locked_brief: str = ""
    use_llm: bool | None = None


class RahoCommanderGrillBody(BaseModel):
    message: str
    allowed_tools: list[str] = []
    alternative_fields: list[str] = []
    priority_ruling: str = ""
    rounds_used: int = 0
    item_id: str = ""


@app.post("/raho/grill/start")
def raho_grill_start(body: RahoGrillStartBody) -> dict[str, Any]:
    """L5→L4 用戶需求審計官：五維鎖定第一問。"""
    from backend.company.raho.grill_user import grill_user_start, should_grill_user

    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query 不可為空")
    if not should_grill_user(query, body.execution_strategy):
        return {
            "should_grill": False,
            "locked": True,
            "confidence": 1.0,
            "locked_brief": query,
            "session_id": "",
            "question": None,
        }
    try:
        return grill_user_start(query)
    except Exception as exc:
        logger.warning("RAHO grill_start 失敗，降級直通：%s", exc)
        return {
            "should_grill": False,
            "locked": True,
            "confidence": 0.5,
            "locked_brief": query,
            "session_id": "",
            "question": None,
            "degraded": True,
        }


@app.post("/raho/grill/turn")
def raho_grill_turn(body: RahoGrillTurnBody) -> dict[str, Any]:
    """繼續需求審計，或將『直接執行』視為過度授權。"""
    from backend.company.raho.grill_user import grill_user_lock, grill_user_turn

    try:
        if body.force_lock:
            return grill_user_lock(body.session_id, body.answer)
        return grill_user_turn(body.session_id, body.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/raho/grill/status")
def raho_grill_status() -> dict[str, Any]:
    from backend.company.raho.grill_user import grill_user_status

    return grill_user_status()


class AuditorStreamBody(BaseModel):
    query: str = ""
    session_id: str = ""
    answer: str = ""
    force_lock: bool = False


@app.post("/auditor/start")
def auditor_gateway_start(body: RahoGrillStartBody) -> dict[str, Any]:
    """強制前置閘門：直接開審，不因寒暄跳過。"""
    from backend.services.auditor import auditor_start

    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query 不可為空")
    try:
        return auditor_start(query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/auditor/turn")
def auditor_gateway_turn(body: RahoGrillTurnBody) -> dict[str, Any]:
    """繼續需求審計。force_lock 視同過度授權，觸發終止協議。"""
    from backend.services.auditor import auditor_lock, auditor_turn

    try:
        if body.force_lock:
            return auditor_lock(body.session_id, body.answer)
        return auditor_turn(body.session_id, body.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/auditor/status")
def auditor_gateway_status() -> dict[str, Any]:
    from backend.services.auditor import auditor_status

    return auditor_status()


@app.post("/auditor/stream")
def auditor_gateway_stream(body: AuditorStreamBody) -> StreamingResponse:
    """SSE：把審計官本輪拷問與五維評分推給前端。"""
    from backend.services.auditor import auditor_lock, auditor_start, auditor_turn

    def _events():
        try:
            if (body.session_id or "").strip():
                if body.force_lock:
                    result = auditor_lock(body.session_id, body.answer)
                else:
                    result = auditor_turn(body.session_id, body.answer)
            else:
                query = (body.query or "").strip()
                if not query:
                    raise ValueError("query 不可為空")
                result = auditor_start(query)
        except (KeyError, ValueError) as exc:
            yield f"event: error\ndata: {json_mod.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            return
        question = ((result.get("question") or {}) or {}).get("question") or ""
        if question:
            yield f"event: question\ndata: {json_mod.dumps({'text': question}, ensure_ascii=False)}\n\n"
        if result.get("scores"):
            yield f"event: scores\ndata: {json_mod.dumps(result['scores'], ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json_mod.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/raho/tree")
def raho_tree(run_id: str | None = None) -> dict[str, Any]:
    """遞歸質詢樹與決策阻塞點。"""
    from backend.company.raho.store import STORE

    if run_id:
        tree = STORE.get_tree(run_id)
        from backend.company.raho.l0 import kernel_snapshot

        return {
            "tree": tree.to_dict() if tree else None,
            "pending_decisions": [
                p.to_dict() for p in STORE.list_pending(run_id) if p.resolution is None
            ],
            "l0": kernel_snapshot(query=str(getattr(tree, "goal", "") or "")),
        }
    return STORE.snapshot()


@app.get("/raho/l0")
def raho_l0(query: str = "", node_id: str = "") -> dict[str, Any]:
    """L0 環境與記憶核心：記憶軌跡、知識實體、態勢雷達。"""
    from backend.company.raho.l0 import kernel_snapshot

    return kernel_snapshot(query=query, node_id=node_id)


@app.post("/raho/decide")
def raho_decide(body: RahoDecideBody) -> dict[str, Any]:
    """L5 用戶介入熱馬桶圈裁決。"""
    from backend.company.raho.escalation import decide as decide_escalation

    try:
        return decide_escalation(body.decision_id, body.choice, body.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/raho/commander/plan")
def raho_commander_plan(body: RahoCommanderPlanBody) -> dict[str, Any]:
    """L3 戰術指揮官：把 L4 門票拆成原子作戰地圖。"""
    from backend.company.raho.commander import command_from_ticket

    source = body.ticket or body.locked_brief
    if not source:
        raise HTTPException(status_code=422, detail="需要 ticket 或 locked_brief")
    kwargs: dict[str, Any] = {}
    if body.use_llm is not None:
        kwargs["use_llm"] = body.use_llm
    return command_from_ticket(source, **kwargs)


@app.post("/raho/commander/grill")
def raho_commander_grill(body: RahoCommanderGrillBody) -> dict[str, Any]:
    """L3 回應 L2 [GRILL] 質詢（SOP 決策樹）。"""
    from backend.company.raho.commander import command_grill
    from backend.services.commander import increment_grill_round

    rounds = body.rounds_used
    if body.item_id:
        rounds = increment_grill_round(body.item_id) - 1
    return command_grill(
        body.message,
        allowed_tools=body.allowed_tools,
        alternative_fields=body.alternative_fields,
        priority_ruling=body.priority_ruling,
        rounds_used=max(0, rounds),
    )


@app.post("/raho/commander/grill/stream")
def raho_commander_grill_stream(body: RahoCommanderGrillBody) -> StreamingResponse:
    """L3 對 L2 [GRILL] 的即時裁決（SSE）。"""
    from backend.company.raho.commander import command_grill
    from backend.services.commander import increment_grill_round

    def _events():
        rounds = body.rounds_used
        if body.item_id:
            rounds = increment_grill_round(body.item_id) - 1
        result = command_grill(
            body.message,
            allowed_tools=body.allowed_tools,
            alternative_fields=body.alternative_fields,
            priority_ruling=body.priority_ruling,
            rounds_used=max(0, rounds),
        )
        yield f"event: sop\ndata: {json_mod.dumps({'kind': result.get('kind'), 'escalate': result.get('escalate')}, ensure_ascii=False)}\n\n"
        if result.get("reply"):
            yield f"event: reply\ndata: {json_mod.dumps({'text': result['reply']}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json_mod.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/raho/scorecard")
def raho_scorecard() -> dict[str, Any]:
    from backend.company.raho.scorecard import all_metrics

    return {"roles": all_metrics()}


@app.get("/config")
async def get_config():
    """回傳当前 LLM 配置（金鑰脱敏）與可用模型池。"""
    cfg = get_runtime_config()
    pool = public_pool(cfg)
    return {
        "configured": bool(cfg.get("api_key")),
        "api_key": masked_key(cfg.get("api_key", "")),
        "api_base": cfg.get("api_base", ""),
        "model": cfg.get("model", "") or pool.get("model", ""),
        **pool,
    }


@app.post("/config")
async def update_config(req: LlmConfigRequest):
    """動態更新 LLM 配置（即時生效並持久化），隨後刷新可用模型池。"""
    save_runtime_config(api_key=req.api_key, api_base=req.api_base, model=req.model)
    if req.route_strategy:
        set_route_strategy(req.route_strategy)
    if req.default_route_id:
        from backend.core.llm_config import merge_runtime_config

        merge_runtime_config({"default_route_id": req.default_route_id.strip().lower()})
    logger.info("LLM 配置已更新（model=%s, api_base=%s）", req.model, req.api_base)
    try:
        refresh_model_catalog(reason="save")
    except Exception as exc:  # noqa: BLE001
        logger.warning("儲存後刷新模型目錄失敗：%s", exc)
    return await get_config()


@app.get("/config/routes")
async def get_config_routes():
    """多 API 路由清單（金鑰脱敏）。"""
    return public_router_state()


@app.put("/config/routes")
async def replace_config_routes(body: ApiRoutesReplaceBody):
    """整批覆寫 API 路由。"""
    save_routes(
        [r.model_dump() for r in body.api_routes],
        strategy=body.route_strategy,
        default_id=body.default_route_id,
    )
    try:
        refresh_model_catalog(reason="routes")
    except Exception as exc:  # noqa: BLE001
        logger.warning("路由儲存後刷新目錄失敗：%s", exc)
    return public_router_state()


@app.post("/config/routes")
async def upsert_config_route(body: ApiRouteBody):
    """新增或更新一條 API 路由。"""
    route = upsert_route(body.model_dump())
    try:
        refresh_route_catalog(route["id"], reason="save")
    except Exception as exc:  # noqa: BLE001
        logger.warning("路由 %s 刷新目錄失敗：%s", route.get("id"), exc)
    return public_router_state()


@app.delete("/config/routes/{route_id}")
async def delete_config_route(route_id: str):
    delete_route(route_id)
    return public_router_state()


@app.post("/config/routes/{route_id}/refresh")
async def refresh_config_route(route_id: str):
    try:
        return await asyncio.to_thread(refresh_route_catalog, route_id, reason="manual")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"刷新路由目錄失敗：{exc}") from exc


@app.post("/config/routes/{route_id}/test")
async def test_config_route(route_id: str):
    """以指定路由實際呼叫 LLM 驗證連線。"""
    try:
        reply = await asyncio.to_thread(call_llm, "請用兩個字回覆：成功。", temperature=0, route_id=route_id)
        return {"ok": True, "reply": reply.strip(), "route_id": route_id}
    except Exception as exc:
        logger.warning("路由 %s 連線測試失敗：%s", route_id, exc)
        return {"ok": False, "error": str(exc)[:300], "route_id": route_id}


@app.put("/config/strategy")
async def update_route_strategy(body: RouteStrategyBody):
    strategy = set_route_strategy(body.route_strategy)
    if body.default_route_id:
        from backend.core.llm_config import merge_runtime_config

        merge_runtime_config({"default_route_id": body.default_route_id.strip().lower()})
    state = public_router_state()
    state["route_strategy"] = strategy
    return state


class LlmOpsPrefsBody(BaseModel):
    refresh_interval_sec: int


@app.post("/config/models/refresh")
async def refresh_config_models():
    """立刻爬取通用端點 /models 或重建單一廠商靜態池。"""
    try:
        return await asyncio.to_thread(run_ops_once, "manual")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"刷新模型目錄失敗：{exc}") from exc


@app.post("/config/cost-speed/reload")
async def reload_cost_speed_config():
    """熱重載 cost_speed 路由配置（修改 JSON 後無需重啟）。"""
    from backend.core.cost_speed_router import reload_cost_speed

    return await asyncio.to_thread(reload_cost_speed)


@app.put("/config/ops")
async def update_llm_ops(body: LlmOpsPrefsBody):
    """更新模型目錄定時檢查間隔（秒）。"""
    return set_refresh_interval(body.refresh_interval_sec)


@app.get("/monitor/llm-ops")
async def monitor_llm_ops():
    """監控中心：目前 API 鎖定的模型池與定時檢查狀態。"""
    return collect_llm_ops()


@app.get("/monitor/optimization")
async def monitor_optimization():
    """監控中心：P0–P3 性能優化路線圖運行時指標。"""
    return collect_optimization_monitor()


@app.post("/feedback")
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


@app.get("/feedback/stats")
async def feedback_stats():
    """用戶反饋統計摘要。"""
    from backend.core.user_feedback import feedback_stats as _stats

    return _stats()


@app.get("/monitor/hub-snapshot")
async def monitor_hub_snapshot():
    """監控中心彙總快照（REST 降級用，與 /monitor/ws 同結構）。"""
    from backend.services.monitor_hub import collect_monitor_hub

    return await asyncio.to_thread(collect_monitor_hub)


@app.post("/config/test")
async def test_config():
    """以当前配置實際呼叫 LLM 驗證連線。"""
    try:
        reply = await asyncio.to_thread(call_llm, "請用兩個字回覆：成功。", temperature=0)
        return {"ok": True, "reply": reply.strip()}
    except Exception as exc:
        logger.warning("LLM 連線測試失敗：%s", exc)
        return {"ok": False, "error": str(exc)[:300]}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """执行 EvoLoop 统一模式图（支援多輪對話歷史）。"""
    session_id = req.session_id or uuid.uuid4().hex[:12]
    query = req.query
    lock = req.semantic_lock or {}
    if isinstance(lock, dict) and lock.get("locked_brief"):
        query = str(lock["locked_brief"])
    initial_state = {
        "query": query,
        "session_id": session_id,
        "iteration": 0,
        "score": 0.0,
        "current_answer": "",
        "reflection": "",
        "memories": [],
        "history": req.history or [],
        "execution_strategy": req.execution_strategy,
        "company_template": req.company_template,
        "semantic_lock": lock if isinstance(lock, dict) else {},
    }
    result = await evoloop_graph.ainvoke(initial_state)
    return ChatResponse(
        session_id=session_id,
        answer=result.get("current_answer", "") or result.get("final_answer", ""),
        score=result.get("score"),
        iteration=result.get("iteration", 0),
    )


# ==================== 公司模式 SSE 串流（優化 #11） ====================


async def _company_stream(req: ChatRequest):
    """公司運行時 SSE 串流：異步執行 + EventBus 事件推送。

    將公司運行時的生命週期事件轉換為 SSE 事件，
    前端可即時看到分解/執行/審查/整合各階段進度。
    """
    from backend.company.orchestrator import CompanyOrchestrator
    from backend.company.roles import BUILTIN_TEMPLATES
    from backend.company.events import CompanyEvent

    session_id = req.session_id or uuid.uuid4().hex[:12]
    lock = req.semantic_lock or {}
    query = req.query
    if isinstance(lock, dict) and lock.get("locked_brief"):
        query = str(lock["locked_brief"])
    template_name = req.company_template or "quick_task"

    # 選擇組織模板
    config = BUILTIN_TEMPLATES.get(template_name)
    if config is None:
        config = BUILTIN_TEMPLATES["quick_task"]

    orchestrator = CompanyOrchestrator(config)

    # 公司模式思考軌跡：session_id 即軌跡檔名
    from backend.services.trace_logger import TraceLogger

    company_tracer = TraceLogger(session_id)

    # 用 Queue 橋接 EventBus → SSE
    event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def _on_company_event(event: CompanyEvent, data: dict[str, Any]) -> None:
        """EventBus 監聽器：將事件推入 Queue，並回填思考軌跡。"""
        try:
            event_queue.put_nowait({"event": event.value, "data": data})
        except Exception:
            pass
        try:
            et = event.value
            if et == "phase_change":
                company_tracer.log_phase_change(str(data.get("phase", "")), data={k: v for k, v in data.items() if k != "phase"})
            elif et == "work_item_done":
                company_tracer.log_llm_call(
                    prompt=f"[{data.get('assignee', data.get('role', 'role'))}] {str(data.get('title', ''))[:200]}",
                    response=str(data.get("output") or data.get("result") or "")[:8000],
                    phase="execute_review",
                    role=str(data.get("assignee") or data.get("role") or ""),
                    item_id=str(data.get("item_id") or data.get("id") or ""),
                )
            elif et in ("work_item_error", "review_rework", "work_item_escalate"):
                company_tracer.log_custom(et, {k: (str(v)[:500]) for k, v in data.items()})
        except Exception:  # noqa: BLE001
            pass

    orchestrator.events.on(_on_company_event)

    # 後台執行公司任務
    async def _run_company() -> None:
        try:
            result = await orchestrator.execute(query)
            await event_queue.put({"event": "_done", "data": result})
        except Exception as exc:
            await event_queue.put({"event": "_error", "data": {"error": str(exc)}})

    task = asyncio.create_task(_run_company())

    # 階段：啟動
    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'company_start', 'template': template_name}, ensure_ascii=False)}\n\n"

    # 持續從 Queue 讀取事件並推送 SSE
    try:
        while True:
            try:
                msg = await asyncio.wait_for(event_queue.get(), timeout=300)
            except asyncio.TimeoutError:
                yield f"event: error\ndata: {json_mod.dumps({'error': '公司運行時超時（300s）'}, ensure_ascii=False)}\n\n"
                break

            if msg is None:
                break

            evt = msg["event"]
            data = msg["data"]

            if evt == "_done":
                # 公司執行完成 → 進入反思迴圈
                final_output = data.get("final_output", "")
                company_result = data

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'company_done', 'success': data.get('success', False)}, ensure_ascii=False)}\n\n"

                # 將公司產出交給反思閉環評估
                eval_state = {
                    "query": query,
                    "current_answer": final_output,
                    "session_id": session_id,
                    "company_result": company_result,
                }

                # 輸出長度守門：超標時把「精簡」當成額外一輪改進目標（預算由節點控管）
                eval_state.update(await asyncio.to_thread(nodes.enforce_output_length, eval_state))

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                eval_state.update(await asyncio.to_thread(nodes.evaluate_answer, eval_state))
                eval_data = {
                    'score': eval_state.get('score'),
                    'iteration': 0,
                    'multi_dim': eval_state.get('multi_dim_evaluation', {}),
                }
                yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"

                # 反思迴圈
                prev_score = eval_state.get('score', 0.0)
                while (
                    eval_state.get('score', 0.0) < PASS_THRESHOLD
                    and eval_state.get('iteration', 0) < MAX_ITERATIONS
                ) or eval_state.get("length_directive"):
                    cur = eval_state.get('score', 0.0)
                    if eval_state.get('iteration', 0) >= 1:
                        if cur - prev_score < 0.5 and not eval_state.get("length_directive"):
                            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'early_stop', 'reason': '分數提升不足'}, ensure_ascii=False)}\n\n"
                            break
                    prev_score = cur

                    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'reflect', 'iteration': eval_state.get('iteration', 0)})}\n\n"
                    eval_state.update(await asyncio.to_thread(nodes.reflect, eval_state))

                    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'improve', 'iteration': eval_state.get('iteration', 0)})}\n\n"
                    eval_state.update(await asyncio.to_thread(nodes.improve_answer, eval_state))

                    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                    eval_state.update(await asyncio.to_thread(nodes.evaluate_answer, eval_state))
                    eval_data = {
                        'score': eval_state.get('score'),
                        'iteration': eval_state.get('iteration', 0),
                        'multi_dim': eval_state.get('multi_dim_evaluation', {}),
                    }
                    yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"
                    eval_state.update(await asyncio.to_thread(nodes.enforce_output_length, eval_state))

                final_answer = eval_state.get('current_answer', final_output)
                eval_state['final_answer'] = final_answer

                # 存入記憶
                try:
                    await asyncio.to_thread(nodes.save_memory, eval_state)
                except Exception:
                    pass

                yield f"event: done\ndata: {json_mod.dumps({'answer': final_answer, 'score': eval_state.get('score'), 'iteration': eval_state.get('iteration', 0), 'company': company_result.get('stats', {})}, ensure_ascii=False)}\n\n"
                break

            elif evt == "_error":
                yield f"event: error\ndata: {json_mod.dumps({'error': data.get('error', '未知錯誤')}, ensure_ascii=False)}\n\n"
                break

            else:
                # 公司生命週期事件 → 推送給前端
                yield f"event: company\ndata: {json_mod.dumps({'event': evt, **data}, ensure_ascii=False)}\n\n"

    finally:
        task.cancel()


# ==================== 串流聊天 API（SSE 打字機效果） ====================


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE 串流聊天：即時推送階段進度與生成 token。

    事件格式（Server-Sent Events）：
      event: phase      → 階段切換 {"phase": "..."}
      event: token      → 生成片段 {"token": "..."}
      event: evaluation → 評分 {"score": n, "iteration": n}
      event: done       → 完成 {"answer": "...", "score": n, "iteration": n}
      event: error      → 錯誤 {"error": "..."}

    統一模式：複雜任務（公司運行時路徑）自動降級為同步 /chat。
    """
    from backend.core.company_nodes import _is_complex_task

    if req.execution_strategy == "company" or (
        req.execution_strategy == "auto" and _is_complex_task(req.query)
    ):
        # 公司運行時：SSE 串流進度（優化 #11）
        return StreamingResponse(
            _company_stream(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    session_id = req.session_id or uuid.uuid4().hex[:12]

    # 思考軌跡回填（session_id 即軌跡檔名；前端「軌跡」按鈕以此查詢）
    from backend.services.trace_logger import TraceLogger, eval_trace_kwargs as _eval_trace_kwargs

    chat_tracer = TraceLogger(session_id)

    async def event_stream():
        state: dict[str, Any] = {
            "query": req.query,
            "session_id": session_id,
            "task_id": session_id,
            "history": req.history or [],
            "semantic_lock": req.semantic_lock or {},
        }
        lock = req.semantic_lock or {}
        if isinstance(lock, dict) and lock.get("locked_brief"):
            state["query"] = str(lock["locked_brief"])
        try:
            # 階段 1：記憶檢索
            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'retrieve_memories'})}\n\n"
            chat_tracer.log_phase_change("retrieve_memories")
            state.update(await asyncio.to_thread(nodes.retrieve_memories, state))
            _mems = state.get("retrieved_memories") or []
            if _mems:
                chat_tracer.log_context_injection(
                    source="memory", items=_mems, phase="retrieve_memories", query=state["query"],
                )

            # 階段 2：生成回答（串流 token，Queue 橋接同步生成器與非同步迴圈）
            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'generate'})}\n\n"
            chat_tracer.log_phase_change("generate")
            from backend.prompts import templates
            gen_prompt = templates.GENERATE_INITIAL_ANSWER.format(
                query=state["query"],
                history_context=nodes._format_history(state.get("history", [])),
                memory_context=nodes._format_memories(state.get("retrieved_memories", [])),
            )
            # 與管線節點同一套環節路由，軌跡才能記到真實模型
            from backend.core.stage_router import resolve_stage_model

            gen_model = resolve_stage_model(
                "generate",
                query=state["query"],
                complexity=state.get("task_complexity"),
            )
            loop = asyncio.get_running_loop()
            token_queue: asyncio.Queue[str | None] = asyncio.Queue()
            gen_started = time.monotonic()

            def _produce_tokens() -> None:
                try:
                    for token in call_llm_stream(gen_prompt, system=templates.GENERATE_INITIAL_ANSWER_SYSTEM, model=gen_model):
                        loop.call_soon_threadsafe(token_queue.put_nowait, token)
                finally:
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)

            asyncio.get_running_loop().run_in_executor(None, _produce_tokens)

            answer_parts: list[str] = []
            while True:
                token = await token_queue.get()
                if token is None:
                    break
                answer_parts.append(token)
                yield f"event: token\ndata: {json_mod.dumps({'token': token}, ensure_ascii=False)}\n\n"
            answer = "".join(answer_parts)
            gen_thinking, visible = split_thinking(answer)
            state.update({
                "initial_answer": visible or answer,
                "current_answer": visible or answer,
                "iteration": 0,
                "thinking": gen_thinking,
            })
            chat_tracer.log_llm_call(
                prompt=gen_prompt, response=(visible or answer)[:8000],
                model=gen_model,
                system=templates.GENERATE_INITIAL_ANSWER_SYSTEM,
                duration_ms=round((time.monotonic() - gen_started) * 1000, 1),
                phase="generate",
            )

            # 輸出長度守門：超標時把「精簡」當成額外一輪改進目標（預算由節點控管）
            state.update(await asyncio.to_thread(nodes.enforce_output_length, state))

            # 階段 3：多維度評估（優化 #1 + #4）
            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
            chat_tracer.log_phase_change("evaluate")
            state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
            eval_data = {
                'score': state.get('score'),
                'iteration': 0,
                'multi_dim': state.get('multi_dim_evaluation', {}),
            }
            chat_tracer.log_evaluation(
                state.get('score'), iteration=0,
                **_eval_trace_kwargs(state.get('multi_dim_evaluation')),
            )
            yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"

            # 反思/改進迴圈（動態迭代：帶分數變化率檢測；長度指令未消化時強制多跑一輪）
            prev_score = state.get('score', 0.0)
            while (
                state.get("score", 0.0) < PASS_THRESHOLD
                and state.get("iteration", 0) < MAX_ITERATIONS
            ) or state.get("length_directive"):
                current_score = state.get('score', 0.0)
                # 動態迭代檢查：分數變化率過低時提前終止（優化 #4）
                if state.get('iteration', 0) >= 1:
                    improvement = current_score - prev_score
                    if improvement < 0.5 and not state.get("length_directive"):  # MIN_SCORE_IMPROVEMENT
                        yield f"event: phase\ndata: {json_mod.dumps({'phase': 'early_stop', 'reason': f'分數提升不足 ({improvement:.1f})', 'iteration': state.get('iteration', 0)})}\n\n"
                        break
                prev_score = current_score

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'reflect', 'iteration': state.get('iteration', 0), 'score': current_score})}\n\n"
                chat_tracer.log_phase_change("reflect", data={"iteration": state.get("iteration", 0), "score": current_score})
                state.update(await asyncio.to_thread(nodes.reflect, state))
                critique = str(state.get("critique") or "")
                suggestion = str(state.get("suggestion") or "")
                if critique or suggestion:
                    chat_tracer.log_reflection(
                        "\n".join(x for x in (f"反思：{critique}", f"改進建議：{suggestion}") if x),
                        iteration=state.get("iteration", 0),
                    )
                reflect_text = "\n".join(
                    p for p in (
                        f"反思：{critique}" if critique else "",
                        f"改進建議：{suggestion}" if suggestion else "",
                    ) if p
                )
                if reflect_text:
                    think_token = f"<think>\n{reflect_text}\n</think>\n"
                    yield f"event: token\ndata: {json_mod.dumps({'token': think_token}, ensure_ascii=False)}\n\n"
                    state["thinking"] = "\n\n".join(
                        x for x in (str(state.get("thinking") or ""), reflect_text) if x
                    )

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'improve', 'iteration': state.get('iteration', 0)})}\n\n"
                chat_tracer.log_phase_change("improve", data={"iteration": state.get("iteration", 0)})
                state.update(await asyncio.to_thread(nodes.improve_answer, state))
                improved = str(state.get("current_answer") or "")
                if improved:
                    chat_tracer.log_improvement(
                        improved, iteration=state.get("iteration", 0),
                        based_on_reflection=critique or suggestion,
                    )
                imp_think, imp_vis = split_thinking(improved)
                if imp_think:
                    state["thinking"] = "\n\n".join(
                        x for x in (str(state.get("thinking") or ""), imp_think) if x
                    )
                    state["current_answer"] = imp_vis or improved
                if improved:
                    body = imp_vis or improved
                    yield f"event: answer\ndata: {json_mod.dumps({'answer': body}, ensure_ascii=False)}\n\n"

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
                chat_tracer.log_evaluation(
                    state.get('score'), iteration=state.get('iteration', 0),
                    **_eval_trace_kwargs(state.get('multi_dim_evaluation')),
                )
                eval_data = {
                    'score': state.get('score'),
                    'iteration': state.get('iteration', 0),
                    'multi_dim': state.get('multi_dim_evaluation', {}),
                }
                yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"
                state.update(await asyncio.to_thread(nodes.enforce_output_length, state))

            final_answer = state.get("current_answer", "")
            chat_tracer.log_phase_change("done", data={"score": state.get("score"), "iteration": state.get("iteration", 0)})
            # 儲存記憶（盡力而為）
            state["final_answer"] = final_answer
            await asyncio.to_thread(nodes.save_memory, state)

            yield f"event: done\ndata: {json_mod.dumps({'answer': final_answer, 'thinking': state.get('thinking', ''), 'score': state.get('score'), 'iteration': state.get('iteration', 0)}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.error("串流聊天失敗：%s", exc)
            yield f"event: error\ndata: {json_mod.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 任務介面 API（後台執行 + 進度輪詢） ====================

@app.post("/tasks")
async def create_task(req: TaskRequest):
    """建立後台任務（統一模式），回傳 task_id 供輪詢。

    統一模式下不再區分模式，execution_strategy 僅為可選的強制指定：
    - "auto"（預設）: 系統自動判斷執行路徑
    - "simple": 強制單次 LLM 生成
    - "company": 強制公司運行時
    """
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="query 不可為空")
    record = task_manager.create_task(
        req.query, req.execution_strategy, req.company_template, options=req.options
    )
    task_manager.start_task(record)
    return {"task_id": record.task_id, "strategy": req.execution_strategy}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, events_limit: int = 50):
    """查詢任務進度：狀態、階段、事件流、看板、預算與結果。

    events_limit：回傳最近 N 條事件（0 或負值＝全部）。
    回應另帶 events_total 與 events_truncated 供前端提示截斷。
    """
    record = task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return record.to_dict(events_limit=events_limit)


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """請求取消執行中的任務。

    設置取消標誌，任務會在下一個檢查點中止。
    已完成/已失敗的任務無法取消。
    """
    ok, message = task_manager.cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@app.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """斷點續跑：從檢查點恢復任務執行。

    僅支援公司模式任務（有 orchestrator checkpoint）。
    """
    ok, message = task_manager.resume_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


# ==================== 思考過程軌跡 API ====================

from backend.services.trace_logger import (
    list_checkpoints,
    list_traces,
    load_checkpoint,
    read_trace,
    trace_event_counts,
)


@app.get("/tasks/{task_id}/trace")
async def get_task_trace(
    task_id: str,
    limit: int = 100,
    offset: int = 0,
    event: str | None = None,
    role: str | None = None,
    item_id: str | None = None,
    with_counts: bool = False,
):
    """獲取任務的思考過程記錄（分頁 + 可篩選）。

    記錄內容：LLM 調用、上下文注入、評估、反思、改進、階段切換，
    以及公司模式鏡像的全部角色事件（work_item_*/tool_*/review_*/grill_* 等）。
    event/role 支援逗號分隔多值；with_counts=true 附帶各事件型條數統計。
    """
    events = await asyncio.to_thread(
        read_trace, task_id, limit, offset,
        event=event, role=role, item_id=item_id,
    )
    result: dict = {"task_id": task_id, "offset": offset, "limit": limit, "events": events}
    if with_counts:
        result["event_counts"] = await asyncio.to_thread(trace_event_counts, task_id)
    return result


@app.get("/tasks/{task_id}/checkpoint")
async def get_task_checkpoint(task_id: str):
    """獲取任務的檢查點信息。"""
    checkpoint = await asyncio.to_thread(load_checkpoint, task_id)
    if checkpoint is None:
        return {"task_id": task_id, "exists": False}
    return {"task_id": task_id, "exists": True, "checkpoint": checkpoint}


@app.get("/traces")
async def get_traces(limit: int = 80):
    """列出所有思考過程軌跡檔案摘要。"""
    traces = await asyncio.to_thread(list_traces, limit)
    return {"traces": traces}


@app.get("/checkpoints")
async def get_checkpoints():
    """列出所有可恢復的檢查點。"""
    checkpoints = await asyncio.to_thread(list_checkpoints)
    return {"checkpoints": checkpoints}


@app.websocket("/tasks/{task_id}/ws")
async def task_websocket(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送任务进度。

    客户端连接后自动订阅任务事件，收到消息格式：
    {"task_id": "...", "event": "phase_change|evaluation|task_finished|...", "data": {...}}

    任务完成/失败后发送 task_finished 事件，客户端可主动关闭连接。
    """
    if not ws_authorized(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return

    # 检查任务是否存在
    record = task_manager.get_task(task_id)
    if record is None:
        await websocket.close(code=4004, reason="任务不存在")
        return

    await websocket.accept()
    await task_broadcaster.subscribe(task_id, websocket)

    try:
        # 发送当前状态作为初始快照
        await websocket.send_json({
            "task_id": task_id,
            "event": "snapshot",
            "data": record.to_dict(),
        })

        # 保持连接，等待客户端关闭或任务完成
        while True:
            try:
                # 接收客户端消息（心跳或关闭请求）
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"task_id": task_id, "event": "pong", "data": {}})
                elif data == "close":
                    break
            except WebSocketDisconnect:
                break
    finally:
        await task_broadcaster.unsubscribe(task_id, websocket)


@app.websocket("/monitor/ws")
async def monitor_hub_websocket(websocket: WebSocket):
    """監控中心彙總推送：每 3 秒推送一次 hub-snapshot。

    訊息格式：{"event": "snapshot"|"pong", "data": {...}}
    """
    from backend.services.monitor_hub import collect_monitor_hub

    if not ws_authorized(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return

    await websocket.accept()
    try:
        while True:
            snap = await asyncio.to_thread(collect_monitor_hub)
            await websocket.send_json({"event": "snapshot", "data": snap})

            # 同時接受心跳；最多等待 3 秒再推下一幀
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=3.0)
                if data == "close":
                    break
                if data == "ping":
                    await websocket.send_json({"event": "pong", "data": {}})
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass


# ==================== 記憶庫管理 API ====================

from backend.memory.vector_store import VectorMemoryStore

_memory_store_api = VectorMemoryStore()


def _json_memories() -> list[dict]:
    from backend.memory.json_store import JsonMemoryStore

    rows: list[dict] = []
    for item in JsonMemoryStore().all():
        meta = item.get("metadata") or {}
        rec_id = str(item.get("id") or meta.get("_id") or "")
        if not rec_id:
            rec_id = str(abs(hash(item.get("text") or "")))
        rows.append(
            {
                "id": rec_id,
                "text": item.get("text") or "",
                "metadata": meta,
            }
        )
    return rows


@app.get("/memories")
async def list_memories(limit: int = 100, offset: int = 0):
    """列出記憶庫中的記憶（分頁，按建立時間降序）。"""
    chroma_error = ""
    try:
        all_memories = await asyncio.to_thread(_memory_store_api.all)
    except Exception as exc:  # noqa: BLE001
        logger.warning("記憶庫讀取失敗：%s", exc)
        chroma_error = str(exc)
        all_memories = []
    if not all_memories:
        all_memories = await asyncio.to_thread(_json_memories)
    total = len(all_memories)
    all_memories.sort(
        key=lambda m: (m.get("metadata") or {}).get("created_at", ""),
        reverse=True,
    )
    page = all_memories[offset : offset + limit]
    payload: dict = {"total": total, "offset": offset, "limit": limit, "memories": page}
    if chroma_error and not page:
        payload["error"] = chroma_error
    return payload


@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """刪除單條記憶。"""
    try:
        collection = await asyncio.to_thread(_memory_store_api._get_collection)
        collection.delete(ids=[memory_id])
        _memory_store_api.invalidate_cache()
        return {"deleted": True, "id": memory_id}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"刪除失敗：{exc}") from exc


@app.post("/memories/cleanup")
async def cleanup_memories(max_age_days: int = 30, min_score: float | None = None):
    """清理過期或低品質記憶。"""
    try:
        deleted = await asyncio.to_thread(
            _memory_store_api.cleanup, max_age_days, min_score
        )
        return {"deleted_count": deleted}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"清理失敗：{exc}") from exc


@app.get("/dashboard")
async def dashboard():
    """控制面版聚合資料：統計/任務/存檔/OPC 審計/能力註冊表。"""
    return collect_dashboard()


@app.get("/monitor/opc")
async def monitor_opc():
    """監控中心 OPC 分頁：護欄、審計、即時標籤、最近 6 級任務。"""
    return collect_opc_monitor()


@app.get("/monitor/hub")
async def monitor_hub():
    """監控中心 AI Hub 分頁：探針、熔斷、呼叫日誌、預算。"""
    return collect_hub_monitor()


class RoleSettingsBody(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    system_prompt: str | None = None
    responsibilities: list[str] | None = None
    default_tier: str | None = None
    max_parallel_work: int | None = None
    preferred_model: str | None = None
    preferred_provider: str | None = None
    daily_budget_usd: float | None = None
    weekly_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    cloud_daily_budget_usd: float | None = None
    cloud_weekly_budget_usd: float | None = None
    cloud_monthly_budget_usd: float | None = None
    tools_allowed: list[str] | None = None
    notes: str | None = None
    reporting_to: str | None = None
    can_delegate_to: list[str] | None = None
    alert_on_error: bool | None = None
    alert_on_budget: bool | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    timeout_ms: int | None = None
    routing_strategy: str | None = None
    failover_models: list[str] | None = None
    sla_latency_ms: int | None = None
    max_retries: int | None = None
    alert_on_sla: bool | None = None
    level: int | None = None
    category: str | None = None
    language: str | None = None
    always_require_review: bool | None = None
    priority: int | None = None
    description: str | None = None
    max_daily_items: int | None = None
    require_human_approval: bool | None = None
    stream_enabled: bool | None = None
    cache_enabled: bool | None = None
    pii_redact: bool | None = None
    mainland_only: bool | None = None
    heartbeat_sec: int | None = None
    on_call: bool | None = None
    tags: list[str] | None = None
    notify_channel: str | None = None
    quiet_hours: str | None = None
    context_window: int | None = None
    allow_tool_use: bool | None = None
    auto_escalate: bool | None = None


class CustomRoleBody(BaseModel):
    id: str = ""
    name: str
    clone_from: str | None = None
    level: int = 3
    category: str = "management"
    reporting_to: str | None = None
    can_delegate_to: list[str] = []
    responsibilities: list[str] = []
    system_prompt: str = ""
    max_parallel_work: int = 2
    default_tier: str = "routine"
    preferred_model: str = ""
    preferred_provider: str = ""
    daily_budget_usd: float = 0
    weekly_budget_usd: float = 0
    monthly_budget_usd: float = 0
    cloud_daily_budget_usd: float = 0
    cloud_weekly_budget_usd: float = 0
    cloud_monthly_budget_usd: float = 0
    tools_allowed: list[str] = []
    notes: str = ""
    enabled: bool = True
    alert_on_error: bool = True
    alert_on_budget: bool = True
    alert_on_sla: bool = True
    temperature: float = 0.7
    max_output_tokens: int = 4096
    timeout_ms: int = 120000
    routing_strategy: str = "quality_first"
    failover_models: list[str] = []
    sla_latency_ms: int = 0
    max_retries: int = 3
    language: str = "zh-TW"
    always_require_review: bool = False
    priority: int = 3
    description: str = ""
    max_daily_items: int = 0
    require_human_approval: bool = False
    stream_enabled: bool = True
    cache_enabled: bool = True
    pii_redact: bool = True
    mainland_only: bool = False
    heartbeat_sec: int = 0
    on_call: bool = False
    tags: list[str] = []
    notify_channel: str = ""
    quiet_hours: str = ""
    context_window: int = 0
    allow_tool_use: bool = True
    auto_escalate: bool = True


class MonitorPrefsBody(BaseModel):
    poll_interval_ms: int | None = None
    show_disabled: bool | None = None
    show_idle: bool | None = None
    show_custom_only: bool | None = None
    group_by: str | None = None
    compact_cards: bool | None = None
    default_desk_tab: str | None = None
    sort_by: str | None = None
    capacity_warn_pct: int | None = None
    show_prompt_preview: bool | None = None
    highlight_alerts: bool | None = None
    auto_open_busy: bool | None = None
    default_layout: str | None = None
    sound_on_alert: bool | None = None
    show_cost_in_cards: bool | None = None
    pin_role_ids: list[str] | None = None
    filter_min_level: int | None = None
    filter_max_level: int | None = None
    timezone: str | None = None
    show_on_call_only: bool | None = None


@app.get("/monitor/agents")
async def monitor_agents():
    """監控中心角色 Agent：每位公司角色獨立任務列表與監控。"""
    return collect_agent_monitor()


@app.put("/monitor/agents/prefs")
async def monitor_agents_prefs(body: MonitorPrefsBody):
    """更新角色監控顯示偏好（輪詢間隔、是否顯示停用／待命）。"""
    try:
        return update_monitor_prefs(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/monitor/agents/{role_id}/settings")
async def monitor_agent_settings(role_id: str, body: RoleSettingsBody):
    """更新指定角色的設定（提示詞、模型、預算、啟用狀態）。"""
    try:
        return update_role_settings(role_id, body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/monitor/agents/{role_id}/reset")
async def monitor_agent_reset(role_id: str):
    """還原內建角色設定為系統預設。"""
    try:
        return reset_role_settings(role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/monitor/agents")
async def monitor_agents_create(body: CustomRoleBody):
    """新增自定義角色（出現在監控中心，可編輯完整角色設定）。"""
    try:
        return create_custom_role(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/monitor/agents/{role_id}")
async def monitor_agents_delete(role_id: str):
    """刪除自定義角色。內建角色不可刪，請改為停用。"""
    try:
        delete_custom_role(role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "id": role_id}


# ==================== 公司運行時：席位 I/O 監察餵給 API ====================

_SEAT_TEXT_FIELDS = ("system", "prompt", "response")


def _seat_row_light(row: dict) -> dict:
    """列表用輕量投影：正文換成預覽＋長度，單條全文另取。"""
    light = {k: v for k, v in row.items() if k not in _SEAT_TEXT_FIELDS}
    for field in _SEAT_TEXT_FIELDS:
        text = str(row.get(field) or "")
        light[f"{field}_preview"] = text[:320]
        light[f"{field}_length"] = int(row.get(f"{field}_length") or len(text))
    return light


@app.get("/monitor/raho/feed")
def raho_seat_feed(
    task_id: str = "",
    run_id: str = "",
    role: str = "",
    layer: int | None = None,
    item_id: str = "",
    kind: str = "",
    limit: int = 120,
    full: bool = False,
):
    """席位投遞餵給：公司模式監察頁的單一資料源。

    每一筆 = 一次真正投遞給模型的調用（含重試與工具閉環的逐輪）。
    預設回傳輕量投影（正文僅預覽）；full=true 或走單條端點取全文。
    環形緩衝查不到時，自動回退到持久 seat_<run_id>.jsonl（跨重啟可查）。
    """
    from backend.company.seat_io import STORE

    rows = STORE.list(
        run_id=run_id,
        task_id=task_id,
        role=role,
        layer=layer,
        item_id=item_id,
        limit=limit,
    )
    source = "memory"
    if not rows and run_id:
        rows = STORE.load_run(run_id, limit=limit)
        source = "disk"
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return {
        "items": rows if full else [_seat_row_light(r) for r in rows],
        "source": source,
        "runs": STORE.recent_runs(limit=20),
        "total_roles": len({r.get("role") for r in rows if r.get("role")}),
    }


@app.get("/monitor/raho/seat/{io_id}")
def raho_seat_detail(io_id: str):
    """單次席位投遞全文（系統提示詞／組裝 prompt／模型回應／來源分解）。"""
    from backend.company.seat_io import STORE

    row = STORE.get(io_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投遞軌跡不存在")
    return row


# ==================== Docker 容器管理 API ====================

@app.get("/docker/status")
async def docker_status():
    """獲取 Docker 容器狀態摘要（含按時計費費率）。"""
    dm = get_docker_manager()
    return {
        "available": dm.available,
        "containers": dm.list_containers(),
        "health": dm.health_check() if dm.available else {"_error": "Docker 不可用"},
        "hourly_rates": DOCKER_SERVICE_HOURLY_RATES,
    }


@app.get("/docker/budget")
async def docker_budget():
    """獲取 Docker 容器預算狀態（公司全權控制）。

    返回當前 Docker 成本、預算壓力、優化建議和自動優化記錄。
    """
    from backend.company.docker_tools import get_service_hourly_rate

    dm = get_docker_manager()

    # 計算當前容器運行成本
    services: list[dict[str, Any]] = []
    total_docker_cost = 0.0
    total_hourly_rate = 0.0

    if dm.available:
        for c in dm.list_containers():
            svc = c.get("service", c["name"])
            if svc == "_docker_unavailable":
                continue
            rate = get_service_hourly_rate(svc)
            uptime_s = float(c.get("uptime_seconds", 0))
            hours = uptime_s / 3600.0
            cost = rate * hours
            is_running = c.get("status", "").startswith("Up")
            services.append({
                "service": svc,
                "rate_per_hour": rate,
                "uptime_hours": round(hours, 2),
                "cost": round(cost, 4),
                "status": "running" if is_running else "stopped",
            })
            if is_running:
                total_docker_cost += cost
                total_hourly_rate += rate

    return {
        "available": dm.available,
        "services": services,
        "total_docker_cost": round(total_docker_cost, 4),
        "total_hourly_rate": round(total_hourly_rate, 4),
        "monthly_projection": round(total_hourly_rate * 24 * 30, 4),
        "company_budget": _company_budget_state,
    }


@app.get("/docker/containers")
async def docker_containers():
    """列出所有容器。"""
    dm = get_docker_manager()
    return {"containers": dm.list_containers()}


@app.get("/docker/logs/{service}")
async def docker_logs(service: str, tail: int = 100):
    """獲取指定服務的日誌。"""
    dm = get_docker_manager()
    logs = dm.get_container_logs(service, tail=tail)
    return {"service": service, "tail": tail, "logs": logs}


@app.get("/docker/stats")
async def docker_stats():
    """獲取容器資源使用統計。"""
    dm = get_docker_manager()
    return {"stats": dm.get_stats()}


@app.get("/docker/health")
async def docker_health():
    """檢查所有服務健康狀態。"""
    dm = get_docker_manager()
    return dm.health_check()


@app.post("/docker/restart/{service}")
async def docker_restart(service: str):
    """重啟指定服務。"""
    dm = get_docker_manager()
    return dm.restart_service(service)


@app.post("/docker/stop/{service}")
async def docker_stop(service: str):
    """停止指定服務。"""
    dm = get_docker_manager()
    return dm.stop_service(service)


@app.post("/docker/start/{service}")
async def docker_start(service: str):
    """啟動指定服務。"""
    dm = get_docker_manager()
    return dm.start_service(service)


# ==================== 雲控制台 API ====================


@app.get("/cloud/billing")
async def cloud_billing():
    """獲取雲端費用摘要（Docker 按時計費 + 阿里雲 BSS）。"""
    billing = get_cloud_billing()
    return billing.get_billing_summary()


@app.get("/cloud/aliyun")
async def cloud_aliyun_status():
    """阿里雲 BSS 接入狀態與本月帳目。"""
    from backend.services.aliyun_bss import get_aliyun_bss

    return get_aliyun_bss().get_billing_overview(force=True)


@app.get("/cloud/monitoring")
async def cloud_monitoring(range: str = "1h"):
    """獲取資源監控歷史數據。

    Args:
        range: 時間範圍（1h / 6h / 24h）
    """
    range_map = {"1h": 1.0, "6h": 6.0, "24h": 24.0}
    hours = range_map.get(range, 1.0)
    monitor = get_cloud_monitor()
    return monitor.get_history(hours)


@app.get("/cloud/monitoring/latest")
async def cloud_monitoring_latest():
    """獲取最新資源快照。"""
    monitor = get_cloud_monitor()
    data = monitor.get_latest()
    if data is None:
        return {"services": {}, "ts": None}
    return data


@app.get("/cloud/events")
async def cloud_events(limit: int = 50):
    """獲取容器事件時間線。"""
    events = get_cloud_events()
    return {"events": events.get_events(limit)}


@app.get("/cloud/alerts")
async def cloud_alerts_list():
    """獲取告警規則列表。"""
    alerts = get_cloud_alerts()
    return {
        "rules": alerts.list_rules(),
        "history": alerts.get_alert_history(50),
    }


class AlertRuleCreate(BaseModel):
    name: str
    metric: str  # cpu / memory
    threshold: float
    service: str = "*"


@app.post("/cloud/alerts")
async def cloud_alerts_create(rule: AlertRuleCreate):
    """創建告警規則。"""
    alerts = get_cloud_alerts()
    return alerts.create_rule(
        name=rule.name,
        metric=rule.metric,
        threshold=rule.threshold,
        service=rule.service,
    )


@app.post("/cloud/alerts/{rule_id}/toggle")
async def cloud_alerts_toggle(rule_id: str):
    """切換告警規則啟用狀態。"""
    alerts = get_cloud_alerts()
    result = alerts.toggle_rule(rule_id)
    if result is None:
        raise HTTPException(status_code=404, detail="規則不存在")
    return result


@app.delete("/cloud/alerts/{rule_id}")
async def cloud_alerts_delete(rule_id: str):
    """刪除告警規則。"""
    alerts = get_cloud_alerts()
    if not alerts.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="規則不存在")
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════
# 實驗室整合 — Firecrawl / Prompt Optimizer / Ponytail / Archify
# ═══════════════════════════════════════════════════════════════


class FirecrawlScrapeRequest(BaseModel):
    url: str
    only_main_content: bool = True


class FirecrawlSearchRequest(BaseModel):
    query: str
    limit: int = 5


class PromptOptimizeRequest(BaseModel):
    prompt: str
    mode: str = "user"
    goal: str = ""


class PonytailReviewRequest(BaseModel):
    content: str
    kind: str = "code"


class ArchifyGenerateRequest(BaseModel):
    description: str


class ArchifyRenderRequest(BaseModel):
    ir: dict[str, Any] = {}
    view: str = ""
    id: str = ""
    kind: str = ""


@app.post("/lab/firecrawl/scrape")
async def lab_firecrawl_scrape(body: FirecrawlScrapeRequest):
    """Firecrawl 單頁抓取（可選 API 金鑰）。"""
    try:
        return lab_tools.firecrawl_scrape(body.url, only_main_content=body.only_main_content)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Firecrawl HTTP {exc.response.status_code}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/lab/firecrawl/search")
async def lab_firecrawl_search(body: FirecrawlSearchRequest):
    """Firecrawl 網頁搜尋（需 FIRECRAWL_API_KEY）。"""
    try:
        return lab_tools.firecrawl_search(body.query, limit=body.limit)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Firecrawl HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/lab/prompt/optimize")
async def lab_prompt_optimize(body: PromptOptimizeRequest):
    """Prompt Optimizer — LLM 提示詞優化。"""
    try:
        return lab_tools.optimize_prompt(body.prompt, mode=body.mode, goal=body.goal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/lab/ponytail/review")
async def lab_ponytail_review(body: PonytailReviewRequest):
    """Ponytail — 過度工程審查。"""
    try:
        return lab_tools.ponytail_review(body.content, kind=body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/lab/archify/evoloop")
async def lab_archify_evoloop():
    """Archify — EvoLoop 內建架構 IR。"""
    return lab_tools.get_evoloop_architecture()


@app.post("/lab/archify/generate")
async def lab_archify_generate(body: ArchifyGenerateRequest):
    """Archify — 由描述生成架構 IR。"""
    try:
        return lab_tools.generate_architecture(body.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _archify_public(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "html": payload["html"],
        "diagram_type": payload.get("diagram_type"),
        "title": payload.get("title"),
        "engine": payload.get("engine") or "archify",
        "source": payload.get("source"),
    }


@app.get("/lab/archify/html")
async def lab_archify_html(view: str = "overview", id: str = "", kind: str = ""):
    """用官方 archify CLI 把策略庫／系統圖編成獨立 HTML。"""
    from backend.company.archify_compile import render_view

    try:
        return _archify_public(render_view(view=view, id=id, kind=kind))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/lab/archify/artifact")
async def lab_archify_artifact(view: str = "overview", id: str = "", kind: str = ""):
    """同一張策略圖，直接回 Archify HTML（iframe / 另開分頁）。"""
    from backend.company.archify_compile import render_view

    try:
        payload = render_view(view=view, id=id, kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as orig:
        raise HTTPException(status_code=503, detail=str(orig)) from orig
    except Exception as orig:
        raise HTTPException(status_code=502, detail=str(orig)) from orig
    return HTMLResponse(payload["html"], media_type="text/html; charset=utf-8")


@app.post("/lab/archify/render")
async def lab_archify_render(body: ArchifyRenderRequest):
    """把簡化 IR（或正式 Archify JSON）交給 archify CLI 渲染。"""
    from backend.company.archify_compile import render_ir, render_view

    try:
        if body.ir:
            return _archify_public(render_ir(body.ir))
        return _archify_public(render_view(view=body.view, id=body.id, kind=body.kind))
    except ValueError as orig:
        raise HTTPException(status_code=400, detail=str(orig)) from orig
    except FileNotFoundError as orig:
        raise HTTPException(status_code=503, detail=str(orig)) from orig
    except Exception as orig:
        raise HTTPException(status_code=502, detail=str(orig)) from orig


@app.get("/lab/archify/strategies")
async def lab_archify_strategies():
    """Archify — 策略庫總覽／分類拓撲 IR（全部策略可視化）。"""
    from backend.company.quant_strategy_maps import strategy_catalog_maps

    return strategy_catalog_maps()


@app.get("/lab/archify/strategies/{strategy_id}")
async def lab_archify_strategy(strategy_id: str):
    """Archify — 單策略工作流／生命週期 IR。"""
    from backend.company.quant_strategy_maps import strategy_maps

    payload = strategy_maps(strategy_id)
    if not payload.get("ok"):
        raise HTTPException(status_code=404, detail=payload.get("error") or "未知策略")
    return payload


@app.get("/lab/quant/strategies")
async def lab_quant_strategies(category: str = "", query: str = "", status: str = ""):
    """stock-quant 策略庫分類樹（實驗室瀏覽；角色仍用 market_strategy_catalog）。"""
    from backend.company.quant_strategy_catalog import market_strategy_catalog

    return market_strategy_catalog(
        category=category,
        query=query,
        status=status,
        listing=True,
    )


@app.get("/lab/quant/preview")
async def lab_quant_preview(strategy: str, symbol: str = "600519"):
    """策略工作流 IR + 回測權益／收盤曲線（實驗室圖表）。"""
    from backend.company.quant_strategy_maps import strategy_preview

    payload = strategy_preview(strategy, symbol=symbol)
    if not payload.get("ok"):
        raise HTTPException(status_code=404, detail=payload.get("error") or "未知策略")
    return payload


@app.get("/lab/quant/capital-flow")
async def lab_quant_capital_flow(
    strategy: str,
    symbol: str = "600519",
    initial_capital: float = 1_000_000.0,
    stop_loss_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    position_pct: float | None = None,
    enable_t1: bool = False,
):
    """策略資金流三視圖：瀑布 Mermaid、狀態機 Mermaid、時間軸表。"""
    from backend.company.quant_capital_flow_maps import strategy_capital_flow

    payload = strategy_capital_flow(
        strategy,
        symbol=symbol,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        trailing_stop_pct=trailing_stop_pct,
        position_pct=position_pct,
        enable_t1=enable_t1,
    )
    if not payload.get("ok"):
        raise HTTPException(status_code=404, detail=payload.get("error") or "未知策略")
    return payload


# ═══════════════════════════════════════════════════════════
# 數據庫連接池管理 API（供 UI 使用）
# ═══════════════════════════════════════════════════════════

from backend.hub.db import Database

class DbPoolRefreshRequest(BaseModel):
    min_idle: int = 2

@app.get("/admin/db/pool/stats")
async def get_db_pool_stats():
    """獲取數據庫連接池統計信息。"""
    return Database.get_pool_stats()

@app.post("/admin/db/pool/refresh")
async def refresh_db_pool(body: DbPoolRefreshRequest):
    """刷新連接池（關閉空閒連接）。"""
    return Database.refresh_pool(body.min_idle)

@app.delete("/admin/db/pool/connection/{connection_id}")
async def close_db_connection(connection_id: str):
    """關閉指定連接。"""
    success = Database.close_connection(connection_id)
    if not success:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"success": True}

@app.post("/admin/db/health")
async def run_db_health_check():
    """執行數據庫健康檢查。"""
    return Database.run_health_check()


# ═══════════════════════════════════════════════════════════
# 技能庫 API（Skills）— 注入角色提示詞的可重用知識
# ═══════════════════════════════════════════════════════════

from backend.company.skills import skills_store


class SkillBody(BaseModel):
    id: str | None = None
    name: str
    content: str
    description: str = ""
    trigger: str = ""
    enabled: bool = True
    roles: list[str] = []
    skill_budget: int = 2400


@app.get("/skills")
async def list_skills():
    """列出全部技能。"""
    return {"skills": [s.to_dict() for s in skills_store.list()]}


@app.post("/skills")
async def save_skill(body: SkillBody):
    """新增／更新技能（upsert）。"""
    try:
        skill = skills_store.upsert(
            body.name,
            body.content,
            skill_id=body.id,
            description=body.description,
            trigger=body.trigger,
            enabled=body.enabled,
            roles=body.roles,
            skill_budget=body.skill_budget,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "skill": skill.to_dict()}


@app.post("/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str):
    """啟用／停用技能。"""
    skill = skills_store.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    updated = skills_store.set_enabled(skill_id, not skill.enabled)
    return {"ok": True, "skill": updated.to_dict()}


@app.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """刪除技能。"""
    if not skills_store.delete(skill_id):
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, "deleted": skill_id}


@app.get("/skills/preview")
async def preview_skill_prompt(role: str | None = None):
    """預覽某角色實際會被注入的技能區塊（除錯用）。"""
    return {"role": role or "*", "prompt": skills_store.render_prompt(role)}


# ═══════════════════════════════════════════════════════════
# MCP 連線管理 API — 通用 MCP server 註冊／探測／工具掛載
# ═══════════════════════════════════════════════════════════

from backend.company.mcp_clients import mcp_registry


class McpServerBody(BaseModel):
    id: str | None = None
    name: str
    transport: str = "stdio"
    command: str = ""
    env: dict[str, str] = {}
    url: str = ""
    headers: dict[str, str] = {}
    enabled: bool = True
    allowed_tools: list[str] = []
    readonly: bool = True
    timeout: float = 20.0


class McpCallBody(BaseModel):
    tool: str
    args: dict[str, Any] = {}


@app.get("/mcp/servers")
async def list_mcp_servers():
    """列出全部 MCP server 與最近探測結果。"""
    return {"servers": [s.to_dict() for s in mcp_registry.list()]}


@app.post("/mcp/servers")
async def save_mcp_server(body: McpServerBody):
    """新增／更新 MCP server（upsert）。"""
    try:
        srv = mcp_registry.upsert(
            body.name,
            body.transport,
            server_id=body.id,
            command=body.command,
            env=body.env,
            url=body.url,
            headers=body.headers,
            enabled=body.enabled,
            allowed_tools=body.allowed_tools,
            readonly=body.readonly,
            timeout=body.timeout,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "server": srv.to_dict()}


@app.post("/mcp/servers/{server_id}/toggle")
async def toggle_mcp_server(server_id: str):
    """啟用／停用 server。"""
    srv = mcp_registry.get(server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="server 不存在")
    updated = mcp_registry.set_enabled(server_id, not srv.enabled)
    return {"ok": True, "server": updated.to_dict()}


@app.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """刪除 server。"""
    if not mcp_registry.delete(server_id):
        raise HTTPException(status_code=404, detail="server 不存在")
    return {"ok": True, "deleted": server_id}


@app.post("/mcp/servers/{server_id}/probe")
async def probe_mcp_server(server_id: str):
    """探測連線並回傳工具清單。"""
    try:
        result = await asyncio.to_thread(mcp_registry.probe, server_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="server 不存在") from None
    return result


@app.post("/mcp/servers/{server_id}/call")
async def call_mcp_tool(server_id: str, body: McpCallBody):
    """手動呼叫工具（測試用；角色執行走 tool_registry 閉環）。"""
    try:
        result = await asyncio.to_thread(mcp_registry.call, server_id, body.tool, body.args)
    except KeyError:
        raise HTTPException(status_code=404, detail="server 不存在")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    return {"ok": True, "result": str(result)[:8000]}


@app.post("/mcp/mount")
async def mount_mcp_tools():
    """把啟用 server 的工具掛進公司工具註冊表（啟動時也會自動跑）。"""
    from backend.company.tools import tool_registry

    mounted = await asyncio.to_thread(mcp_registry.mount_tools, tool_registry, force=True)
    return {"ok": True, "mounted": mounted, "count": len(mounted)}


@app.get("/mcp/tools")
async def list_mcp_tools():
    """列出目前已掛載的 MCP 工具（含內建總數）。"""
    from backend.company.tools import tool_registry

    rows = [
        {"name": t.name, "description": t.description, "readonly": t.readonly}
        for t in tool_registry.list_tools()
        if t.name.startswith(tuple(f"{s.id}__" for s in mcp_registry.list()))
    ] if mcp_registry.list() else []
    return {"tools": rows, "total_registry": len(tool_registry.list_tools())}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
