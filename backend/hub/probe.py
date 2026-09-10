"""廠商延遲 / 價格探針。每 30 秒對目錄模型發 8 token ping，寫入 provider:metrics。"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

from backend.core.llm import call_llm
from backend.hub.catalog import HUB_CATALOG, PRICE_PER_1M, seed_default_metrics
from backend.hub.runtime import runtime

PROBE_INTERVAL_S = 30.0
PING_MAX_TOKENS = 8
CONNECT_TIMEOUT_S = 2.0
READ_TIMEOUT_S = 5.0
EWMA_ALPHA = 0.3
FAIL_PENALTY_MS = 15000.0
PING_PROMPT = "ping"


def _ewma(prev: float, sample: float) -> float:
    return (1.0 - EWMA_ALPHA) * prev + EWMA_ALPHA * sample


def probe_once(llm: Callable[..., str] | None = None) -> dict[str, dict[str, Any]]:
    """對九模型各發一次 ping，更新 EWMA。失敗則 latency_ewma_ms=15000。"""
    invoke = llm or call_llm
    seed_default_metrics(runtime.store.provider_metrics)
    now = int(time.time())
    for model in sorted(HUB_CATALOG):
        row = runtime.store.provider_metrics[model]
        t0 = time.monotonic()
        try:
            invoke(
                prompt=PING_PROMPT,
                system=None,
                model=model,
                max_retries=1,
                timeout=CONNECT_TIMEOUT_S + READ_TIMEOUT_S,
                max_tokens=PING_MAX_TOKENS,
            )
            sample_ms = (time.monotonic() - t0) * 1000.0
            row["latency_ewma_ms"] = _ewma(float(row.get("latency_ewma_ms") or sample_ms), sample_ms)
            row["ttfb_ms"] = sample_ms
            row["consecutive_fail"] = 0
        except Exception:
            row["latency_ewma_ms"] = FAIL_PENALTY_MS
            row["consecutive_fail"] = int(row.get("consecutive_fail") or 0) + 1
        in_p, out_p = PRICE_PER_1M[model]
        row["price_in_per_1m"] = in_p
        row["price_out_per_1m"] = out_p
        row["ts"] = now
        runtime.store.provider_metrics[model] = row
    return dict(runtime.store.provider_metrics)


class ProbeScheduler:
    """單執行緒週期探針。測試預設不啟動；生產設 HUB_PROBE_ENABLED=1。"""

    def __init__(self, interval_s: float = PROBE_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hub-probe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            probe_once()
            self._stop.wait(self.interval_s)


_scheduler: ProbeScheduler | None = None


def maybe_start_probe() -> ProbeScheduler | None:
    global _scheduler
    if os.environ.get("HUB_PROBE_ENABLED", "").strip() not in {"1", "true", "TRUE", "yes"}:
        return None
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    seed_default_metrics(runtime.store.provider_metrics)
    _scheduler = ProbeScheduler()
    _scheduler.start()
    return _scheduler
