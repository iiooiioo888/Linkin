"""ModelGW P3/#132：FAILED 後最小補償三件（可 stub）。

順序硬鎖：delete_isvc → release_cloudcore_lease → notify_upstream。
預設 LoggingCompensationSink＝結構化 log／no-op；禁標成生產 K8s 補償。
補償不得改回 PROVISIONING*；永不回滾 FAILED。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

COMPENSATE_OK = "ok"
COMPENSATE_RETRYABLE = "retryable"
COMPENSATE_SKIPPED = "skipped"
COMPENSATE_STATUSES = frozenset({COMPENSATE_OK, COMPENSATE_RETRYABLE, COMPENSATE_SKIPPED})


class CompensationSink(Protocol):
    def delete_isvc(self, model_id: str, meta: dict[str, Any]) -> str:
        """回傳 ok｜retryable｜skipped。"""
        ...

    def release_lease(self, lease_id: str | None, model_id: str) -> str: ...

    def notify_upstream(self, model_id: str, reason: str) -> str: ...


class LoggingCompensationSink:
    """預設 stub：結構化 log + no-op，三件皆回 ok。"""

    def delete_isvc(self, model_id: str, meta: dict[str, Any]) -> str:
        logger.info(
            "MODELGW compensate stub delete_isvc model_id=%s meta_keys=%s",
            model_id,
            sorted(meta.keys()) if meta else [],
        )
        return COMPENSATE_OK

    def release_lease(self, lease_id: str | None, model_id: str) -> str:
        logger.info(
            "MODELGW compensate stub release_lease model_id=%s lease_id=%s",
            model_id,
            lease_id or "",
        )
        return COMPENSATE_OK

    def notify_upstream(self, model_id: str, reason: str) -> str:
        logger.info(
            "MODELGW compensate stub notify_upstream model_id=%s reason=%s",
            model_id,
            reason,
        )
        return COMPENSATE_OK


def run_compensation(
    sink: CompensationSink,
    *,
    model_id: str,
    lease_id: str | None,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> str:
    """依序跑三件；任一 retryable／拋錯 → retryable；全 skipped → skipped；否則 ok。"""
    meta = dict(meta or {})
    results: list[str] = []
    steps = (
        ("delete_isvc", lambda: sink.delete_isvc(model_id, meta)),
        ("release_lease", lambda: sink.release_lease(lease_id, model_id)),
        ("notify_upstream", lambda: sink.notify_upstream(model_id, reason)),
    )
    for name, fn in steps:
        try:
            status = str(fn() or COMPENSATE_OK).strip().lower()
            if status not in COMPENSATE_STATUSES:
                status = COMPENSATE_RETRYABLE
            results.append(status)
            logger.debug("MODELGW compensate step=%s status=%s model_id=%s", name, status, model_id)
        except Exception as exc:
            logger.warning(
                "MODELGW compensate step=%s failed model_id=%s: %s",
                name,
                model_id,
                exc,
            )
            results.append(COMPENSATE_RETRYABLE)

    if any(r == COMPENSATE_RETRYABLE for r in results):
        return COMPENSATE_RETRYABLE
    if all(r == COMPENSATE_SKIPPED for r in results):
        return COMPENSATE_SKIPPED
    return COMPENSATE_OK


__all__ = [
    "COMPENSATE_OK",
    "COMPENSATE_RETRYABLE",
    "COMPENSATE_SKIPPED",
    "COMPENSATE_STATUSES",
    "CompensationSink",
    "LoggingCompensationSink",
    "run_compensation",
]
