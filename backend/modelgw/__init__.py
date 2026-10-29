"""ModelGW（O21）：動態 Registry 準入 + Hub 風格熔斷／探針（機制級對齊）。

純庫契約不變。HTTP／call_llm 掛載見 api.py／runtime.py（MODELGW_WIRE_MODE，預設 off）。
不讀 HUB_CATALOG、不 import hub.circuit。
對齊 linkin-audit/modelgw-hub-gap-20261029.md §5／§8.1。
"""

from __future__ import annotations

from backend.modelgw.admission import AdmitDecision, AdmitResult, admit
from backend.modelgw.errors import ModelGWError
from backend.modelgw.registry import InMemoryRegistry, ModelRecord, ModelStatus
from backend.modelgw.service import InvokeResult, ModelGWService

__all__ = [
    "AdmitDecision",
    "AdmitResult",
    "InMemoryRegistry",
    "InvokeResult",
    "ModelGWError",
    "ModelGWService",
    "ModelRecord",
    "ModelStatus",
    "admit",
]
