"""EvoLoop 后端 FastAPI 入口（應用組裝層）。

啟動方式：
    python -m backend.main
    uvicorn backend.main:app --host 0.0.0.0 --port 8000

重構後職責：只負責建立 FastAPI app、註冊 middleware／例外處理／lifespan，
以及把領域路由（backend/api/routers/*）掛上 app；端點實作不在本檔。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ═══════════════════════════════════════════════════════════════
# 向後相容 re-export（既有測試／外部程式會從 backend.main import）
# ═══════════════════════════════════════════════════════════════
from backend.api.security import _client_identity  # noqa: F401
from backend.billing import register_billing
from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
from backend.billing.middleware import BillingContextMiddleware
from backend.core import nodes  # noqa: F401  # tests patch backend.main.nodes.*
from backend.hub.api import register_hub
from backend.linkin.api import register_linkin
from backend.middleware.auth_gate import AuthGateMiddleware
from backend.modules import register_modules
from backend.services.llm_ops import llm_ops_loop
from backend.services.task_manager import task_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    from backend.core.opc_degrade import reset_opc_health

    reset_opc_health()
    # 重啟回灌：從 Redis 載回任務記錄，修復任務列表／管線重啟後清空
    try:
        await asyncio.to_thread(task_manager.rehydrate)
    except Exception as exc:
        logger.warning("任務 rehydrate 失敗（降級為記憶體）：%s", exc)
    try:
        from backend.services.cancelled_task_cleanup import cleanup_enabled, run_cleanup

        if cleanup_enabled():
            await asyncio.to_thread(run_cleanup, task_manager)
    except Exception as exc:
        logger.warning("啟動時已取消任務清理失敗：%s", exc)
    # 主 loop 註冊：供 MCP server 等無 loop 執行緒安全派發任務
    task_manager._loop = asyncio.get_running_loop()
    from backend.ephemeral_containers.config import ephemeral_containers_enabled
    from backend.ephemeral_containers.worker import container_task_worker

    if ephemeral_containers_enabled():
        container_task_worker.bind_loop(asyncio.get_running_loop())
        container_task_worker.start()
        logger.info("臨時容器 worker 已啟動（EVOL_EPHEMERAL_CONTAINERS）")
    # 技能庫與 MCP：載入設定並把啟用 server 的工具掛進 tool_registry
    try:
        from backend.company.mcp_clients import mcp_registry
        from backend.company.skills import skills_store
        from backend.company.tools import tool_registry

        skills_store.load()
        from backend.company.agent_skills_sync import sync_on_boot

        boot_report = await asyncio.to_thread(sync_on_boot)
        if boot_report is not None:
            logger.info("Agent 技能包啟動同步：%s", boot_report.to_dict())
        mounted = await asyncio.to_thread(mcp_registry.mount_tools, tool_registry)
        if mounted:
            logger.info("啟動掛載 MCP 工具 %d 個", len(mounted))
    except Exception as exc:
        logger.warning("技能／MCP 啟動掛載失敗（降級為無）：%s", exc)
    task = asyncio.create_task(llm_ops_loop())
    from backend.billing.docker_meter import docker_billing_loop

    docker_bill_task = asyncio.create_task(docker_billing_loop())

    async def _rollover_loop() -> None:
        import os

        from backend.billing.pool_store import get_pool_store

        interval = max(3600, int(os.getenv("LINKIN_ROLLOVER_CHECK_SEC", "86400")))
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(get_pool_store().run_monthly_rollover)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("月末滾存檢查失敗：%s", exc)

    rollover_task = asyncio.create_task(_rollover_loop())

    async def _contribution_maintenance_loop() -> None:
        from backend.billing.contribution_service import (
            process_due_installments,
            run_contribution_decay,
        )

        installment_interval = max(3600, int(os.getenv("LINKIN_INSTALLMENT_CHECK_SEC", "3600")))
        decay_interval = max(3600, int(os.getenv("LINKIN_DECAY_CHECK_SEC", "86400")))
        tick = 0
        while True:
            try:
                await asyncio.sleep(installment_interval)
                tick += 1
                await asyncio.to_thread(process_due_installments)
                if tick * installment_interval >= decay_interval:
                    await asyncio.to_thread(run_contribution_decay)
                    tick = 0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("貢獻積分維護檢查失敗：%s", exc)

    contribution_task = asyncio.create_task(_contribution_maintenance_loop())

    async def _cancelled_task_cleanup_loop() -> None:
        from backend.services.cancelled_task_cleanup import (
            cleanup_enabled,
            cleanup_interval_seconds,
            run_cleanup,
        )

        if not cleanup_enabled():
            return
        interval = cleanup_interval_seconds()
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(run_cleanup, task_manager)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("已取消任務清理失敗：%s", exc)

    cleanup_task = asyncio.create_task(_cancelled_task_cleanup_loop())
    ect_worker_stop = None
    if ephemeral_containers_enabled():
        ect_worker_stop = container_task_worker
    try:
        yield
    finally:
        if ect_worker_stop is not None:
            await ect_worker_stop.stop()
        cleanup_task.cancel()
        contribution_task.cancel()
        rollover_task.cancel()
        docker_bill_task.cancel()
        task.cancel()
        try:
            await contribution_task
        except asyncio.CancelledError:
            pass
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        try:
            await rollover_task
        except asyncio.CancelledError:
            pass
        try:
            await docker_bill_task
        except asyncio.CancelledError:
            pass
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

app.add_middleware(BillingContextMiddleware)
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
from backend.ephemeral_containers.api import register_ephemeral_containers

register_ephemeral_containers(app)
register_modules(app)
from backend.integrations.api import register_integrations

register_integrations(app)
from backend.company.runtime_api import register_runtime_api

register_runtime_api(app)
register_billing(app)
from backend.mediacrawler import register_mediacrawler

register_mediacrawler(app)
@app.exception_handler(InsufficientCreditsError)
async def billing_insufficient_handler(_request: Request, exc: InsufficientCreditsError):
    return JSONResponse(
        status_code=402,
        content={
            "detail": exc.message,
            "code": exc.code,
            "balance_credits": exc.balance_credits,
            "required_credits": exc.required_credits,
        },
    )


@app.exception_handler(FeatureNotEntitledError)
async def billing_feature_handler(_request: Request, exc: FeatureNotEntitledError):
    return JSONResponse(
        status_code=403,
        content={
            "detail": exc.message,
            "code": exc.code,
            "feature": exc.feature,
            "plan_id": exc.plan_id,
        },
    )


@app.exception_handler(PermissionError)
async def tenant_permission_handler(_request: Request, exc: PermissionError):
    return JSONResponse(status_code=401, content={"detail": str(exc) or "未登入或租戶無效"})



# ═══════════════════════════════════════════════════════════════
# API 路由裝配（實作在 backend/api/routers/*）
# ═══════════════════════════════════════════════════════════════
from backend.api.routers import (
    chat as chat_routes,
)
from backend.api.routers import (
    config as config_routes,
)
from backend.api.routers import (
    db_admin as db_admin_routes,
)
from backend.api.routers import (
    docker_cloud as docker_cloud_routes,
)
from backend.api.routers import (
    health_auth as health_auth_routes,
)
from backend.api.routers import (
    lab as lab_routes,
)
from backend.api.routers import (
    memories as memories_routes,
)
from backend.api.routers import (
    monitor as monitor_routes,
)
from backend.api.routers import (
    raho_auditor as raho_auditor_routes,
)
from backend.api.routers import (
    skills_mcp as skills_mcp_routes,
)
from backend.api.routers import (
    tasks as tasks_routes,
)

app.include_router(health_auth_routes.router)
app.include_router(raho_auditor_routes.router)
app.include_router(config_routes.router)
app.include_router(chat_routes.router)
app.include_router(tasks_routes.router)
app.include_router(memories_routes.router)
app.include_router(monitor_routes.router)
app.include_router(docker_cloud_routes.router)
app.include_router(db_admin_routes.router)
app.include_router(lab_routes.router)
app.include_router(skills_mcp_routes.router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
