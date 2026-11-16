"""聊天與路由預覽的請求／回應模型。"""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from backend.core.execution_path import ExternalStrategyError, prepare_executing_strategy


def require_chat_strategy(raw: str | None) -> str:
    """聊天會執行。auto 與 suggest_only 在進圖之前拒絕。"""
    try:
        return prepare_executing_strategy(raw)
    except ExternalStrategyError as exc:
        token = exc.token
        if token == "auto":
            raise HTTPException(
                status_code=422,
                detail=(
                    "execution_strategy 不再接受 auto。"
                    "請改用 simple、company 或 user_default。"
                    "建議請查 GET /tasks/path-suggestion。"
                ),
            ) from exc
        if token == "suggest_only":
            raise HTTPException(
                status_code=422,
                detail="聊天會直接執行，不接受 suggest_only。請改查 GET /tasks/path-suggestion。",
            ) from exc
        raise HTTPException(
            status_code=422,
            detail=f"不支援的 execution_strategy：{token}。允許 simple、company、user_default。",
        ) from exc


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    # 會執行的策略：simple / company / user_default。省略為 simple。
    # auto 與 suggest_only 由 require_chat_strategy 拒絕，不進圖。
    execution_strategy: str = "simple"
    company_template: str = "quick_task"
    # 多輪對話歷史：[{"role": "user"|"assistant", "content": "..."}, ...]
    history: list[dict[str, str]] = []
    # 前端 i18n（zh-TW / en）→ 約束回覆語言
    ui_language: str | None = None
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


class RoutingPreviewRequest(BaseModel):
    query: str
    # auto 只代表「沿用建議規則做預覽」，不建立任務，也不當執行策略。
    mode: str = "auto"
    context: dict[str, Any] | None = None
    company_template: str | None = None
