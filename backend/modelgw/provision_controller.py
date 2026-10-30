"""ModelGW P3/#132：PROVISIONING* 超時 → FAILED ＋補償（同進程 poller）。

硬鎖：
- 超時只認 extras.provision_started_at（G-P3-CLOCK1）；禁只用 updated_at
- 缺欄 → 一次 backfill=now＋audit clock_backfill=true
- 補償-only：status==FAILED AND compensate_status==retryable
- 永不回滾 FAILED；WIRE／enforce 不動
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from backend.modelgw.compensate import (
    COMPENSATE_RETRYABLE,
    LoggingCompensationSink,
    run_compensation,
)
from backend.modelgw.registry import (
    PROVISIONING_STATUSES,
    ModelRecord,
    ModelStatus,
    Registry,
)

logger = logging.getLogger(__name__)

FAIL_REASON_TIMEOUT = "provision_timeout"
EXTRA_STARTED = "provision_started_at"
EXTRA_FAIL_REASON = "fail_reason"
EXTRA_COMPENSATE = "compensate_status"

_DEFAULT_TIMEOUT = 600
_DEFAULT_POLL = 30
_TIMEOUT_MIN = 60
_TIMEOUT_MAX = 3600


def provision_timeout_sec() -> int:
    raw = (os.getenv("MODELGW_PROVISION_TIMEOUT_SEC") or str(_DEFAULT_TIMEOUT)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_TIMEOUT
    return max(_TIMEOUT_MIN, min(_TIMEOUT_MAX, n))


def provision_poll_sec() -> int:
    raw = (os.getenv("MODELGW_PROVISION_POLL_SEC") or str(_DEFAULT_POLL)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_POLL
    return max(1, n)


def _status_value(rec: ModelRecord) -> str:
    st = rec.status
    if isinstance(st, ModelStatus):
        return st.value
    return str(st).upper()


def _parse_started_at(extras: dict[str, Any]) -> float | None:
    raw = extras.get(EXTRA_STARTED)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


@dataclass
class TickStats:
    scanned: int = 0
    backfilled: int = 0
    timed_out: int = 0
    compensated: int = 0
    errors: list[str] = field(default_factory=list)


def _iter_tenant_records(registry: Registry) -> list[tuple[str, ModelRecord]]:
    """回傳 (tenant_id, record)。SQL 有 all_with_tenant；否則 all()＋tenant=\"\"。"""
    getter = getattr(registry, "all_with_tenant", None)
    if callable(getter):
        rows = getter()
        out: list[tuple[str, ModelRecord]] = []
        for item in rows:
            if isinstance(item, tuple) and len(item) == 2:
                out.append((str(item[0]), item[1]))
        return out
    return [("", r) for r in registry.all()]


def _upsert(registry: Registry, record: ModelRecord, *, tenant_id: str) -> None:
    upsert = getattr(registry, "upsert", None)
    if not callable(upsert):
        raise RuntimeError("registry 無 upsert")
    try:
        upsert(record, tenant_id=tenant_id)
    except TypeError:
        upsert(record)


def ensure_provision_started_at(
    extras: dict[str, Any] | None,
    *,
    now: float | None = None,
    force_reset: bool = False,
) -> dict[str, Any]:
    """進入 PROVISIONING*：首次寫 provision_started_at；force_reset（reprovision）重置。"""
    out = dict(extras or {})
    ts = float(now if now is not None else time.time())
    if force_reset or EXTRA_STARTED not in out or out.get(EXTRA_STARTED) in (None, ""):
        out[EXTRA_STARTED] = ts
    return out


def mark_failed_timeout(record: ModelRecord, *, now: float | None = None) -> ModelRecord:
    extras = dict(record.extras or {})
    extras[EXTRA_FAIL_REASON] = FAIL_REASON_TIMEOUT
    extras[EXTRA_COMPENSATE] = COMPENSATE_RETRYABLE
    record.status = ModelStatus.FAILED
    record.extras = extras
    _ = now
    return record


def _run_compensate_for(
    registry: Registry,
    tenant_id: str,
    record: ModelRecord,
    sink: LoggingCompensationSink,
    *,
    reason: str,
) -> str:
    status = run_compensation(
        sink,
        model_id=record.model_id,
        lease_id=record.lease_id or None,
        reason=reason,
        meta={
            "tenant_id": tenant_id,
            "revision": record.revision,
            "endpoint": record.endpoint,
            "plane": record.plane,
            **dict(record.extras or {}),
        },
    )
    extras = dict(record.extras or {})
    extras[EXTRA_COMPENSATE] = status
    record.extras = extras
    # 維持 FAILED；只更新 compensate_status
    if _status_value(record) != ModelStatus.FAILED.value:
        record.status = ModelStatus.FAILED
    _upsert(registry, record, tenant_id=tenant_id)
    return status


def tick(
    registry: Registry,
    sink: LoggingCompensationSink | None = None,
    *,
    now: float | None = None,
    timeout_sec: int | None = None,
) -> TickStats:
    """單輪：CLOCK1 backfill → 超時寫 FAILED → 補償；再掃補償-only。"""
    sink = sink or LoggingCompensationSink()
    now_ts = float(now if now is not None else time.time())
    timeout = int(timeout_sec if timeout_sec is not None else provision_timeout_sec())
    stats = TickStats()

    for tenant_id, rec in _iter_tenant_records(registry):
        stats.scanned += 1
        status = _status_value(rec)
        extras = dict(rec.extras or {})

        if status in {s.value for s in PROVISIONING_STATUSES}:
            started = _parse_started_at(extras)
            if started is None:
                extras[EXTRA_STARTED] = now_ts
                extras["clock_backfill"] = True
                rec.extras = extras
                _upsert(registry, rec, tenant_id=tenant_id)
                stats.backfilled += 1
                logger.info(
                    "MODELGW provision clock_backfill=true tenant_id=%s model_id=%s",
                    tenant_id,
                    rec.model_id,
                )
                continue
            if (now_ts - started) >= timeout:
                mark_failed_timeout(rec, now=now_ts)
                _upsert(registry, rec, tenant_id=tenant_id)
                stats.timed_out += 1
                logger.info(
                    "MODELGW provision timeout→FAILED tenant_id=%s model_id=%s "
                    "started_at=%s timeout_sec=%s",
                    tenant_id,
                    rec.model_id,
                    started,
                    timeout,
                )
                try:
                    _run_compensate_for(
                        registry,
                        tenant_id,
                        rec,
                        sink,
                        reason=FAIL_REASON_TIMEOUT,
                    )
                    stats.compensated += 1
                except Exception as exc:
                    msg = f"compensate after timeout {rec.model_id}: {exc}"
                    stats.errors.append(msg)
                    logger.warning("MODELGW %s", msg)
            continue

        if status == ModelStatus.FAILED.value:
            cs = str(extras.get(EXTRA_COMPENSATE) or "").strip().lower()
            if cs == COMPENSATE_RETRYABLE:
                reason = str(extras.get(EXTRA_FAIL_REASON) or "failed")
                try:
                    _run_compensate_for(registry, tenant_id, rec, sink, reason=reason)
                    stats.compensated += 1
                except Exception as exc:
                    msg = f"compensate-only {rec.model_id}: {exc}"
                    stats.errors.append(msg)
                    logger.warning("MODELGW %s", msg)

    return stats


_poll_task: asyncio.Task[None] | None = None


async def provision_poll_loop() -> None:
    """backend lifespan 掛載的同進程 interval poller。"""
    from backend.modelgw.runtime import get_service

    sink = LoggingCompensationSink()
    while True:
        try:
            poll = provision_poll_sec()
            await asyncio.sleep(poll)
            reg = get_service().registry
            await asyncio.to_thread(tick, reg, sink)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("MODELGW provision poller 失敗：%s", exc)


def start_provision_poller(loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task[None]:
    """啟動 poller task；測試可 cancel。"""
    global _poll_task
    if _poll_task is not None and not _poll_task.done():
        return _poll_task
    task = asyncio.create_task(provision_poll_loop(), name="modelgw-provision-poller")
    _poll_task = task
    logger.info(
        "MODELGW provision poller 已啟動 timeout_sec=%s poll_sec=%s",
        provision_timeout_sec(),
        provision_poll_sec(),
    )
    return task


def stop_provision_poller() -> asyncio.Task[None] | None:
    global _poll_task
    task = _poll_task
    _poll_task = None
    if task is not None and not task.done():
        task.cancel()
    return task


__all__ = [
    "EXTRA_COMPENSATE",
    "EXTRA_FAIL_REASON",
    "EXTRA_STARTED",
    "FAIL_REASON_TIMEOUT",
    "TickStats",
    "ensure_provision_started_at",
    "mark_failed_timeout",
    "provision_poll_loop",
    "provision_poll_sec",
    "provision_timeout_sec",
    "start_provision_poller",
    "stop_provision_poller",
    "tick",
]
