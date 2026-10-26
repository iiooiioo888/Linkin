"""OPC 服务 FastAPI 应用工厂。

配置 CORS、lifespan（启动模拟器 + 连接 OPC）、挂载路由。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opc_service.config import settings
from opc_service.internal_auth import OpcInternalAuthMiddleware
from opc_service.routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时连接 OPC，关闭时断开连接。"""
    # 启动
    logger.info("OPC 服务启动中...")

    if settings.sim_enabled:
        from opc_service.simulator import start_simulator

        await start_simulator()
        logger.info(
            "模拟 OPC 服务器已启动（port %s）", settings.sim_port
        )

    from opc_service.client import opc_client

    try:
        await opc_client.connect()
    except Exception:
        logger.warning(
            "无法连接至 OPC UA 服务器（%s），将以降级模式运行",
            settings.opc_server_url,
        )

    yield

    # 关闭
    await opc_client.disconnect()
    logger.info("OPC 服务已关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="EvoLoop OPC Service",
        description="OPC 工业数据微服务 — 封装读写、订阅与安全护栏",
        version="0.1.0",
        lifespan=lifespan,
        # FASTAPI-OPENAPI-001：此服務不對瀏覽器公開文件。
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # FASTAPI-CORS-001：只給後端伺服器呼叫，不開瀏覽器跨站。
    app.add_middleware(OpcInternalAuthMiddleware)

    app.include_router(router)

    return app


# 模块级应用实例（供 uvicorn 直接引用）
app = create_app()