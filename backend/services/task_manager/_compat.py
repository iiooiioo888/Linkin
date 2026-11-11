"""測試 patch 相容層：讓 patch 套件層名稱仍然生效。

重構前 task_manager 是單一模組，測試直接替換模組屬性：
  - patch(backend.services.task_manager.TraceLogger)：執行期建立 TraceLogger 須延遲解析。
  - patch.object(task_manager_module, enhance_with_opc_context／enhance_with_linkin_context)
因此執行期一律經過本模組，呼叫當下才解析回套件層屬性。
"""

from __future__ import annotations

from typing import Any


def _package() -> Any:
    """回傳 backend.services.task_manager 套件模組（呼叫當下才匯入，避免循環）。"""
    from backend.services import task_manager as _pkg

    return _pkg


def new_trace_logger(task_id: str) -> Any:
    """延遲解析 TraceLogger：測試會 patch backend.services.task_manager.TraceLogger。"""
    return _package().TraceLogger(task_id)


async def enhance_with_opc_context(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 enhancement：測試以 patch.object 替換套件層函式。"""
    return await _package().enhance_with_opc_context(*args, **kwargs)


def enhance_with_linkin_context(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 enhancement（同步，供 asyncio.to_thread 使用）。"""
    return _package().enhance_with_linkin_context(*args, **kwargs)


def save_checkpoint(task_id: str, data: dict[str, Any]) -> Any:
    """延遲解析檢查點寫入：測試會以 monkeypatch.setattr 替換套件層函式。"""
    return _package().save_checkpoint(task_id, data)


def load_checkpoint(task_id: str) -> Any:
    """延遲解析檢查點讀取（測試 patch 套件層函式）。"""
    return _package().load_checkpoint(task_id)


def delete_checkpoint(task_id: str) -> Any:
    """延遲解析檢查點刪除（測試 patch 套件層函式）。"""
    return _package().delete_checkpoint(task_id)
