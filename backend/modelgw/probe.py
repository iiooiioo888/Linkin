"""延遲探針：掃 Registry READY 集（不讀 HUB_CATALOG）。參數對齊 Hub probe。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from backend.modelgw.registry import Registry

PROBE_INTERVAL_S = 30.0
PING_MAX_TOKENS = 8
CONNECT_TIMEOUT_S = 2.0
READ_TIMEOUT_S = 5.0
EWMA_ALPHA = 0.3
FAIL_PENALTY_MS = 15000.0
PING_PROMPT = "ping"

PROBE_PARAMS: dict[str, float | int | str] = {
    "probe_interval_s": PROBE_INTERVAL_S,
    "ping_max_tokens": PING_MAX_TOKENS,
    "ewma_alpha": EWMA_ALPHA,
    "fail_penalty_ms": FAIL_PENALTY_MS,
}


def _ewma(prev: float, sample: float) -> float:
    return (1.0 - EWMA_ALPHA) * prev + EWMA_ALPHA * sample


def probe_once(
    registry: Registry,
    metrics: dict[str, dict[str, Any]],
    llm: Callable[..., str] | None = None,
) -> dict[str, dict[str, Any]]:
    """對 READY 模型各發一次 ping；失敗則 latency_ewma_ms=15000。

    llm 簽名對齊測試假件：llm(prompt=..., model=..., max_tokens=..., ...) -> str
    未注入 llm 時視為探針失敗（純庫不呼叫上游）。
    """
    now = int(time.time())
    for model_id in registry.ready_ids():
        row = metrics.setdefault(model_id, {})
        t0 = time.monotonic()
        try:
            if llm is None:
                raise RuntimeError("no llm injector")
            llm(
                prompt=PING_PROMPT,
                system=None,
                model=model_id,
                max_retries=1,
                timeout=CONNECT_TIMEOUT_S + READ_TIMEOUT_S,
                max_tokens=PING_MAX_TOKENS,
            )
            sample_ms = (time.monotonic() - t0) * 1000.0
            prev = float(row.get("latency_ewma_ms") or sample_ms)
            row["latency_ewma_ms"] = _ewma(prev, sample_ms)
            row["ttfb_ms"] = sample_ms
            row["consecutive_fail"] = 0
        except Exception:
            row["latency_ewma_ms"] = FAIL_PENALTY_MS
            row["consecutive_fail"] = int(row.get("consecutive_fail") or 0) + 1
        row["ts"] = now
        metrics[model_id] = row
    return dict(metrics)
