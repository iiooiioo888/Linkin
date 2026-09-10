"""可插拔世界／整合模組。

統一契約：``GET /modules``、``/{id}``、``/{id}/pages``、``/{id}/capabilities``、
``/{id}/health``、``/{id}/api/{path}``（轉發至各模組 ``api_prefix``）。

新增模組：
1. 在本套件寫 ``foo.py``，回傳 ``ModuleSpec``（含 nav／capabilities／pages／health）
2. 於 ``register_builtin_modules()`` 呼叫 ``register_*_module()``
3. 把業務路由掛在 ``api_prefix``（寫入必須走該模組護欄）
4. 前端 ``modules/`` 註冊頁面元件；目錄可由 ``GET /modules`` hydrate
5. 客戶端一律打 ``/modules/{id}/api/...``，勿直連控制台路由
"""

from __future__ import annotations

from backend.modules.api import register_module_routes
from backend.modules.minecraft import register_minecraft_module
from backend.modules.registry import get_module, list_modules, register_module, reset_registry


def register_builtin_modules() -> None:
    if get_module("minecraft") is None:
        register_minecraft_module()


def register_modules(app) -> None:
    register_builtin_modules()
    register_module_routes(app)


__all__ = [
    "get_module",
    "list_modules",
    "register_builtin_modules",
    "register_module",
    "register_modules",
    "reset_registry",
]
