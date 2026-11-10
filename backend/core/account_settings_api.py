"""帳號級設定 HTTP：實驗室工具開關。寫入只落在目前登入使用者。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.core.user_settings import (
    active_settings_user,
    guard_settings_write,
    lab_tool_prefs,
    save_lab_tool_prefs,
)

router = APIRouter(prefix="/config/lab", tags=["account-settings"])


class LabPrefsBody(BaseModel):
    mcp_tools: dict[str, bool] = Field(default_factory=dict)


def _payload(tools: dict[str, bool]) -> dict[str, Any]:
    return {
        "mcp_tools": tools,
        "settings_user": active_settings_user() or "",
        "settings_isolated": bool(active_settings_user()),
    }


@router.get("")
def get_lab_prefs() -> dict[str, Any]:
    return _payload(lab_tool_prefs())


@router.put("")
def put_lab_prefs(body: LabPrefsBody) -> dict[str, Any]:
    guard_settings_write()
    saved = save_lab_tool_prefs(body.mcp_tools)
    return _payload(saved)


def register_account_settings(app: Any) -> None:
    app.include_router(router)
