"""統一模組目錄與業務閘道。

契約（後續世界／整合模組共用，不走控制台路由）：

- ``GET /modules``
- ``GET /modules/{id}``
- ``GET /modules/{id}/pages``
- ``GET /modules/{id}/pages/{page}``
- ``GET /modules/{id}/health``
- ``GET /modules/{id}/capabilities``
- ``ANY /modules/{id}/api/{path}`` — 校驗後轉發 ``api_prefix/{path}``
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from backend.modules.gateway import dispatch_module_api
from backend.modules.registry import get_module, list_modules

modules_router = APIRouter(prefix="/modules", tags=["modules"])


def register_module_routes(app) -> None:
    app.include_router(modules_router)


def _require_module(module_id: str):
    spec = get_module(module_id)
    if spec is None or not spec.enabled:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")
    return spec


@modules_router.get("")
def list_world_modules() -> dict[str, Any]:
    specs = list_modules()
    return {
        "modules": [spec.to_dict() for spec in specs],
        "count": len(specs),
    }


@modules_router.get("/{module_id}")
def get_world_module(module_id: str) -> dict[str, Any]:
    return _require_module(module_id).to_dict()


@modules_router.get("/{module_id}/pages")
def list_world_module_pages(module_id: str) -> dict[str, Any]:
    spec = _require_module(module_id)
    return {
        "id": spec.id,
        "default_page": spec.default_page,
        "pages": spec.pages(),
        "count": len(spec.pages()),
    }


@modules_router.get("/{module_id}/pages/{page}")
def get_world_module_page(module_id: str, page: str) -> dict[str, Any]:
    spec = _require_module(module_id)
    item = spec.page(page)
    if item is None:
        raise HTTPException(status_code=404, detail=f"模組頁面不存在：{module_id}/{page}")
    return {"id": spec.id, "page": item}


@modules_router.get("/{module_id}/health")
def get_world_module_health(module_id: str) -> dict[str, Any]:
    return _require_module(module_id).health_snapshot()


@modules_router.get("/{module_id}/capabilities")
def list_world_module_capabilities(module_id: str) -> dict[str, Any]:
    spec = _require_module(module_id)
    return {
        "id": spec.id,
        "api_prefix": spec.api_prefix,
        "gateway_prefix": spec.gateway_prefix(),
        "capabilities": [cap.to_dict() for cap in spec.capabilities],
        "count": len(spec.capabilities),
    }


@modules_router.api_route(
    "/{module_id}/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def world_module_api(module_id: str, path: str, request: Request) -> Response:
    spec = _require_module(module_id)
    return await dispatch_module_api(spec, request, path)
