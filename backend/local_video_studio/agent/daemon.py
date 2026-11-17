"""``python -m backend.local_video_studio.agent``：心跳、租約、優雅停機。"""

from __future__ import annotations

import os
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.local_video_studio.agent.heartbeat import record_heartbeat
from backend.local_video_studio.agent.lease import reclaim_expired_leases
from backend.local_video_studio.agent.poller import run_once
from backend.local_video_studio.config import load_config
from backend.local_video_studio.db import init_db, session_scope


def build_stop_handler(
    stop: threading.Event,
    *,
    agent_id: str,
    storage_base: Path | None,
) -> Callable[[int, object], None]:
    def _handle(signum: int, _frame: object) -> None:
        stop.set()
        record_heartbeat(
            agent_id=agent_id,
            status="shutting_down",
            detail=f"signal {signum}",
            storage_base=storage_base,
        )

    return _handle


def install_signal_handlers(
    stop: threading.Event,
    *,
    agent_id: str,
    storage_base: Path | None,
) -> Callable[[int, object], None]:
    handler = build_stop_handler(stop, agent_id=agent_id, storage_base=storage_base)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    return handler


def _interruptible_sleep(seconds: float, stop: threading.Event) -> None:
    end = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < end:
        if stop.is_set():
            return
        time.sleep(min(0.05, end - time.monotonic()))


def _real_cycle(stop: threading.Event) -> dict[str, Any] | None:
    cfg = load_config()
    root = Path(cfg.storage_base)
    with session_scope() as session:
        reclaim_expired_leases(session, root)
        return run_once(
            session,
            agent_id=cfg.agent_id,
            storage_base=root,
            should_stop=stop.is_set,
        )


def serve(
    *,
    stop_event: threading.Event | None = None,
    max_cycles: int | None = None,
    poll_interval_sec: float | None = None,
    run_once_fn: Callable[..., dict[str, Any] | None] | None = None,
) -> int:
    """輪詢 queued job。``stop_event`` 或訊號置位後，當前等待會退回租約並結束。"""
    cfg = load_config()
    stop = stop_event if stop_event is not None else threading.Event()
    root = Path(cfg.storage_base)
    interval = cfg.agent_poll_interval_sec if poll_interval_sec is None else poll_interval_sec
    cycles = 0
    record_heartbeat(
        agent_id=cfg.agent_id,
        status="starting",
        storage_base=root,
    )
    try:
        while not stop.is_set():
            if max_cycles is not None and cycles >= max_cycles:
                break
            cycles += 1
            record_heartbeat(
                agent_id=cfg.agent_id,
                status="polling",
                storage_base=root,
            )
            if run_once_fn is None:
                result = _real_cycle(stop)
            else:
                result = run_once_fn(should_stop=stop.is_set)
            if stop.is_set():
                break
            if isinstance(result, dict) and result.get("released"):
                break
            _interruptible_sleep(interval, stop)
    finally:
        record_heartbeat(
            agent_id=cfg.agent_id,
            status="stopped",
            detail="graceful shutdown",
            storage_base=root,
        )
        print(f"lvs-agent stopped agent={cfg.agent_id}", flush=True)
    return 0


def main() -> int:
    cfg = load_config()
    init_db()
    stop = threading.Event()
    install_signal_handlers(stop, agent_id=cfg.agent_id, storage_base=Path(cfg.storage_base))
    raw = (os.getenv("LVS_AGENT_MAX_CYCLES") or "").strip()
    max_cycles = int(raw) if raw else None
    print(
        f"lvs-agent start agent={cfg.agent_id} poll={cfg.agent_poll_interval_sec}s "
        f"job_timeout={cfg.job_timeout_sec}s",
        flush=True,
    )
    return serve(stop_event=stop, max_cycles=max_cycles)
