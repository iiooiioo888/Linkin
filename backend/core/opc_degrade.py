"""OPC 降級是否仍在發生。/health 讀這裡，不靠日誌。"""

from __future__ import annotations

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


def opc_health_view() -> dict[str, str]:
    return {"opc_status": _status, "reason": _reason}


def reset_opc_health() -> None:
    note_opc_available()
