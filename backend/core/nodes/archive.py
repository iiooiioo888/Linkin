"""節點 7（自 backend.core.nodes 抽出）。

節點 7：完整對話生命週期存檔。
"""

from __future__ import annotations

import asyncio
import logging

from backend.core.state import StateInput
from backend.services.archiver import save_session_archive, save_session_archive_sync

logger = logging.getLogger(__name__)


def archive_state(state: StateInput) -> dict:
    """節點 7（Task 8.6）：將完整對話生命週期存檔為 JSONL。

    位於圖的最末端，確保狀態已完整；採盡力而為策略，
    存檔失敗只記警告，不影響已產出的最終回答。

    同步節點：目前線程無事件迴圈時以 asyncio.run 執行
    非同步寫入（LangGraph 的 ainvoke 會把同步節點放到
    工作執行緒，該處無事件迴圈，同樣安全）；若偵測到
    執行中的事件迴圈則降級為同步寫入。
    """
    session_id = state.get("session_id", "unknown")
    try:
        try:
            asyncio.run(save_session_archive(state, session_id))
        except RuntimeError:
            # 當前線程已有執行中的事件迴圈，改用同步寫入
            save_session_archive_sync(state, session_id)
        return {"archived": True}
    except Exception as exc:
        logger.warning("對話存檔失敗（不影響回應）：%s", exc)
        return {"archived": False}
