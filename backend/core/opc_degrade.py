"""OPC 降級是否仍在發生。/health 讀這裡，不靠日誌。

多 worker（uvicorn --workers N）時每個進程各有一份 _status；/health 反映的是
**處理該請求的工作進程**狀態，除非只跑單 worker 否則不保證跨進程一致。
契約：工業路徑 sense 失敗後 degraded 為真，直到同進程內 sense 成功或進程重啟。
"""

from __future__ import annotations

from typing import Any

_status = "ok"
_reason = ""


def note_opc_unavailable(reason: str) -> None:
    global _status, _reason
    _status = "unavailable"
    _reason = reason


def note_opc_available() -> None:
    global _status, _reason
    _status = "ok"
    _reason = ""


def note_opc_from_sense_result(result: dict[str, Any]) -> None:
    """依 ``sense_opc`` 回傳同步 process 級 /health OPC 狀態。"""
    if str(result.get("opc_status") or "") == "unavailable":
        note_opc_unavailable(str(result.get("opc_reason") or "OPC 不可用"))
    else:
        note_opc_available()


def opc_health_view() -> dict[str, str]:
    return {"opc_status": _status, "reason": _reason}


def reset_opc_health() -> None:
    note_opc_available()
