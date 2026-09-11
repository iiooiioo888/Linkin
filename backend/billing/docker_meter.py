"""Docker 容器按時計費：即時結算至用戶靈境積分。

策略：
- 用戶透過 API/工具 start/restart 時記錄 service → owner，並預檢餘額
- 背景 tick 依 uptime 增量結算（rate × Δhours → 積分）
- stop 時最終結算並清除 owner
- 積分不足時拒絕新啟動；已運行容器在 tick 結算失敗時停止非核心服務
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from backend.billing.context import billing_enabled, current_billing_user, default_anonymous_user
from backend.billing.credits import credits_for_docker_usd
from backend.billing.errors import InsufficientCreditsError
from backend.billing.metering import meter_docker
from backend.billing.quota import get_billing_service
from backend.company.docker_tools import get_service_hourly_rate

logger = logging.getLogger(__name__)

# 平台核心服務：積分不足時不自動 stop（避免整站不可用）
_CORE_SERVICES = frozenset({"backend", "redis", "chroma"})
_TICK_SEC = float(os.getenv("LINKIN_DOCKER_BILLING_INTERVAL_SEC", "30"))
_MIN_START_MINUTES = float(os.getenv("LINKIN_DOCKER_MIN_START_RESERVE_MIN", "5"))


class DockerBillingTracker:
    """每用戶、每服務的已結算 uptime 追蹤。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # user_id -> service -> last_billed_uptime_seconds
        self._billed_uptime: dict[str, dict[str, float]] = {}
        # service -> owner user_id（API start/restart 記錄）
        self._owners: dict[str, str] = {}
        self._last_tick: float = 0.0

    def assign_owner(self, service: str, user_id: str) -> None:
        with self._lock:
            self._owners[service] = user_id.strip()

    def owner_of(self, service: str) -> str:
        with self._lock:
            return self._owners.get(service) or current_billing_user() or default_anonymous_user()

    def clear_owner(self, service: str) -> str | None:
        with self._lock:
            return self._owners.pop(service, None)

    def ensure_can_start(self, service: str, user_id: str | None = None) -> None:
        """啟動前預檢：至少保留 N 分鐘運行費率對應積分。"""
        if not billing_enabled() and not user_id:
            return
        uid = (user_id or current_billing_user() or default_anonymous_user()).strip()
        rate = get_service_hourly_rate(service)
        reserve_usd = rate * (_MIN_START_MINUTES / 60.0)
        credits = credits_for_docker_usd(reserve_usd)
        if credits <= 0:
            return
        get_billing_service().ensure_can_afford(uid, credits)

    def settle_service(
        self,
        service: str,
        uptime_seconds: float,
        *,
        user_id: str | None = None,
        final: bool = False,
    ) -> dict[str, Any] | None:
        """結算單一服務自上次 tick 以來的增量。"""
        uid = (user_id or self.owner_of(service)).strip()
        if not uid:
            return None
        if not billing_enabled() and not user_id:
            return None

        with self._lock:
            user_state = self._billed_uptime.setdefault(uid, {})
            prev = user_state.get(service, 0.0)
            current = max(0.0, float(uptime_seconds))
            if current <= prev and not final:
                return None
            delta_s = max(0.0, current - prev)
            if final and current < prev:
                # 容器重啟：uptime 重置，結算剩餘 prev 視為已結算
                user_state[service] = current
                return None
            if delta_s <= 0:
                return None
            user_state[service] = current

        delta_h = delta_s / 3600.0
        rate = get_service_hourly_rate(service)
        cost_usd = rate * delta_h
        if cost_usd <= 0:
            return None

        entry = meter_docker(
            service,
            delta_h,
            cost_usd,
            user_id=uid,
            reference=f"docker:{service}",
            meta={
                "service": service,
                "cost_usd": round(cost_usd, 6),
                "delta_hours": round(delta_h, 6),
                "rate_per_hour_usd": rate,
                "final": final,
            },
        )
        return {
            "service": service,
            "user_id": uid,
            "delta_hours": round(delta_h, 6),
            "cost_usd": round(cost_usd, 6),
            "credits": credits_for_docker_usd(cost_usd),
            "entry": entry,
        }

    def settle_tick(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """掃描所有運行中容器，對各 owner 結算增量。"""
        from backend.services.docker_manager import get_docker_manager

        dm = get_docker_manager()
        if not dm.available:
            return []

        charges: list[dict[str, Any]] = []
        broke_users: set[str] = set()

        for c in dm.list_containers():
            svc = c.get("service", c.get("name", ""))
            if not svc or svc == "_docker_unavailable":
                continue
            status = str(c.get("status", ""))
            uptime = float(c.get("uptime_seconds", 0))
            owner = (user_id or self.owner_of(svc)).strip()

            if not status.startswith("Up"):
                if uptime <= 0:
                    prev_owner = self.clear_owner(svc)
                    o = prev_owner or owner
                    with self._lock:
                        self._billed_uptime.get(o, {}).pop(svc, None)
                continue

            try:
                row = self.settle_service(svc, uptime, user_id=owner)
                if row:
                    charges.append(row)
            except InsufficientCreditsError:
                broke_users.add(owner)
                logger.warning("用戶 %s Docker 積分不足，將嘗試停止非核心容器 %s", owner, svc)

        for uid in broke_users:
            self._stop_optional_for_user(uid)

        self._last_tick = time.monotonic()
        return charges

    def on_stop(self, service: str, user_id: str | None = None) -> dict[str, Any] | None:
        """容器停止時最終結算。"""
        from backend.services.docker_manager import get_docker_manager

        uid = (user_id or self.clear_owner(service) or self.owner_of(service)).strip()
        dm = get_docker_manager()
        uptime = 0.0
        if dm.available:
            for c in dm.list_containers():
                svc = c.get("service", c.get("name", ""))
                if svc == service:
                    uptime = float(c.get("uptime_seconds", 0))
                    break
        result = self.settle_service(service, uptime, user_id=uid, final=True)
        with self._lock:
            self._billed_uptime.get(uid, {}).pop(service, None)
            self._owners.pop(service, None)
        return result

    def _stop_optional_for_user(self, user_id: str) -> list[str]:
        """積分耗盡：停止該用戶擁有的非核心容器。"""
        from backend.services.docker_manager import get_docker_manager

        stopped: list[str] = []
        dm = get_docker_manager()
        if not dm.available:
            return stopped

        with self._lock:
            owned = [svc for svc, owner in self._owners.items() if owner == user_id]

        for svc in owned:
            if svc in _CORE_SERVICES:
                continue
            try:
                result = dm.stop_service(svc)
                if result.get("success"):
                    self.on_stop(svc, user_id=user_id)
                    stopped.append(svc)
                    logger.info("積分不足，已停止容器 %s（用戶 %s）", svc, user_id)
            except Exception as exc:
                logger.debug("停止容器 %s 失敗：%s", svc, exc)
        return stopped

    def summary(self, user_id: str | None = None) -> dict[str, Any]:
        from backend.services.docker_manager import get_docker_manager

        uid = (user_id or current_billing_user() or default_anonymous_user()).strip()
        dm = get_docker_manager()
        running: list[dict[str, Any]] = []
        projected_hourly_usd = 0.0
        if dm.available:
            for c in dm.list_containers():
                svc = c.get("service", c.get("name", ""))
                if not svc or svc == "_docker_unavailable":
                    continue
                if not str(c.get("status", "")).startswith("Up"):
                    continue
                rate = get_service_hourly_rate(svc)
                projected_hourly_usd += rate
                running.append(
                    {
                        "service": svc,
                        "owner": self.owner_of(svc),
                        "rate_per_hour_usd": rate,
                        "credits_per_hour": credits_for_docker_usd(rate),
                        "uptime_hours": round(float(c.get("uptime_seconds", 0)) / 3600.0, 4),
                        "is_core": svc in _CORE_SERVICES,
                    }
                )
        return {
            "user_id": uid,
            "running_services": running,
            "projected_hourly_usd": round(projected_hourly_usd, 4),
            "projected_hourly_credits": credits_for_docker_usd(projected_hourly_usd),
            "tick_interval_sec": _TICK_SEC,
            "last_tick_monotonic": self._last_tick,
        }


_TRACKER: DockerBillingTracker | None = None
_TRACKER_LOCK = threading.Lock()


def get_docker_billing_tracker() -> DockerBillingTracker:
    global _TRACKER
    if _TRACKER is None:
        with _TRACKER_LOCK:
            if _TRACKER is None:
                _TRACKER = DockerBillingTracker()
    return _TRACKER


def reset_docker_billing_tracker(tracker: DockerBillingTracker | None = None) -> None:
    global _TRACKER
    with _TRACKER_LOCK:
        _TRACKER = tracker


async def docker_billing_loop() -> None:
    """背景迴圈：定期結算 Docker 運行費用至用戶積分。"""
    if os.getenv("LINKIN_DOCKER_BILLING_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Docker 積分結算迴圈已停用")
        return
    interval = max(5.0, _TICK_SEC)
    tracker = get_docker_billing_tracker()
    while True:
        try:
            import asyncio

            await asyncio.to_thread(tracker.settle_tick)
        except Exception:
            logger.debug("Docker 積分結算 tick 失敗", exc_info=True)
        import asyncio

        await asyncio.sleep(interval)
