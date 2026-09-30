"""在匯入 LangGraph 之前打開嚴格 msgpack。

``langgraph.checkpoint.serde._msgpack`` 在模組載入時讀取
``LANGGRAPH_STRICT_MSGPACK``。因此必須先匯入本模組，再匯入 ``langgraph``。

目前兩張圖都沒有 checkpointer，反序列化路徑不會執行。
此開關是未來若接上 checkpointer 的防線，不能單獨視為 CVE-2025-64439 已修復。
"""

from __future__ import annotations

import os

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
