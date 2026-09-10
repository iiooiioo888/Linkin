"""插件目錄／生命週期 API（含 dsh-context 可視化適配）。

契約：安裝／啟用為顯式 POST；禁止串流自動安裝（C-PLUGIN-001）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.modules.plugin_manager import (
    DSH_CONTEXT_PLUGIN_ID,
    get_plugin_manager,
)

plugins_router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginToggleBody(BaseModel):
    enabled: bool = Field(..., description="True=啟用／False=停用")


def register_plugin_routes(app) -> None:
    app.include_router(plugins_router)


@plugins_router.get("")
def list_plugins() -> dict[str, Any]:
    mgr = get_plugin_manager()
    return {
        "catalog": mgr.catalog(),
        "installed": mgr.list_installed(),
        "count": len(mgr.catalog()),
    }


@plugins_router.get("/catalog")
def get_plugin_catalog() -> dict[str, Any]:
    mgr = get_plugin_manager()
    return {"catalog": mgr.catalog(), "count": len(mgr.catalog())}


@plugins_router.post("/{plugin_id}/install")
def install_plugin(plugin_id: str) -> dict[str, Any]:
    """顯式安裝（目錄項）；dsh-context 為本機適配，不遠端拉取。"""
    mgr = get_plugin_manager()
    out = mgr.install_from_catalog(plugin_id)
    if not out.get("ok"):
        code = out.get("error_code") or "ERR_PLUGIN_INSTALL"
        raise HTTPException(status_code=400, detail={"ok": False, "error_code": code})
    return {**out, "plugin_id": plugin_id, "catalog": mgr.catalog()}


@plugins_router.post("/{plugin_id}/toggle")
def toggle_plugin(plugin_id: str, body: PluginToggleBody) -> dict[str, Any]:
    """顯式啟用／停用。未安裝時啟用會先自動安裝目錄項（仍為顯式 API 動作）。"""
    mgr = get_plugin_manager()
    if plugin_id not in mgr.plugins:
        if not body.enabled:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error_code": "ERR_PLUGIN_NOT_INSTALLED"},
            )
        installed = mgr.install_from_catalog(plugin_id)
        if not installed.get("ok"):
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "error_code": installed.get("error_code")},
            )
    out = mgr.enable(plugin_id) if body.enabled else mgr.disable(plugin_id)
    if not out.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error_code": out.get("error_code")},
        )
    return {
        **out,
        "plugin_id": plugin_id,
        "enabled": body.enabled,
        "context_surfaces": plugin_id == DSH_CONTEXT_PLUGIN_ID,
        "catalog": mgr.catalog(),
    }


@plugins_router.get("/{plugin_id}")
def get_plugin(plugin_id: str) -> dict[str, Any]:
    mgr = get_plugin_manager()
    entry = next((e for e in mgr.catalog() if e["plugin_id"] == plugin_id), None)
    if entry is None and plugin_id not in mgr.plugins:
        raise HTTPException(status_code=404, detail=f"插件不存在：{plugin_id}")
    if entry is None:
        p = mgr.plugins[plugin_id]
        return {
            "plugin_id": plugin_id,
            "repo": p.repo,
            "status": p.status.value,
            "pin_version": p.pin.pin_version,
            "enabled": p.status.value == "enabled",
        }
    return entry
