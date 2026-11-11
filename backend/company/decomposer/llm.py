"""LLM 呼叫輔助：在 worker 執行緒跑同步 LLM，避免凍結 event loop。"""

from __future__ import annotations

import asyncio


async def _llm_thread(fn, *args, **kwargs):
    """worker 執行緒跑同步 LLM；StopIteration 轉 RuntimeError（不得進 Future）。"""
    def _run():
        try:
            return fn(*args, **kwargs)
        except StopIteration as exc:
            raise RuntimeError(f"LLM 呼叫序列耗盡（StopIteration）：{exc}") from exc

    return await asyncio.to_thread(_run)
