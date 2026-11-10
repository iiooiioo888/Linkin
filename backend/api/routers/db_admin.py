"""數據庫連接池管理 API（供 UI 使用）。

自 backend.main 抽出；端點行為與回應結構不變。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.hub.db import Database

router = APIRouter(tags=["db-admin"])


class DbPoolRefreshRequest(BaseModel):
    min_idle: int = 2


@router.get("/admin/db/pool/stats")
async def get_db_pool_stats():
    """獲取數據庫連接池統計信息。"""
    return Database.get_pool_stats()


@router.post("/admin/db/pool/refresh")
async def refresh_db_pool(body: DbPoolRefreshRequest):
    """刷新連接池（關閉空閒連接）。"""
    return Database.refresh_pool(body.min_idle)


@router.delete("/admin/db/pool/connection/{connection_id}")
async def close_db_connection(connection_id: str):
    """關閉指定連接。"""
    success = Database.close_connection(connection_id)
    if not success:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"success": True}


@router.post("/admin/db/health")
async def run_db_health_check():
    """執行數據庫健康檢查。"""
    return Database.run_health_check()
