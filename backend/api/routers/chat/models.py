"""聊天與路由預覽的請求／回應模型。"""

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    # 統一模式：執行策略（auto / simple / company），預設 auto 自動判斷
    execution_strategy: str = "auto"
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
    mode: str = "auto"
    context: dict[str, Any] | None = None
    company_template: str | None = None
