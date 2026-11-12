"""靈境 REST router 建立與 FastAPI 註冊入口。"""

from __future__ import annotations

from fastapi import APIRouter

linkin_router = APIRouter(prefix="/linkin", tags=["linkin"])


def register_linkin(app) -> None:
    app.include_router(linkin_router)
