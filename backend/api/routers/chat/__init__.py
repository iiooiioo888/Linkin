"""聊天、SSE 串流與路由預覽 API 套件（自 backend/api/routers/chat.py 拆出）。

router 於此依原註冊順序組裝：/chat、/routing/preview（routes）→ /chat/stream（streaming）。
"""

from . import routes as routes
from . import streaming as streaming
from ._router import router
from .models import ChatRequest, ChatResponse, RoutingPreviewRequest

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "RoutingPreviewRequest",
    "router",
]
