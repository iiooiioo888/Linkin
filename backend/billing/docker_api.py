"""Docker 計費 API 輔助（供 main.py 掛載 start/stop 前後處理）。"""

from __future__ import annotations

from typing import Any

from backend.auth.gate import gate_enabled
from backend.billing.context import billing_enabled, current_billing_user, default_anonymous_user
from backend.billing.docker_meter import get_docker_billing_tracker


def resolve_docker_user() -> str:
    return current_billing_user() or default_anonymous_user()


def preflight_docker_start(service: str) -> None:
    """Compose 棧 ``/docker/*`` 與 ``docker_*`` 工具的 start/restart 預檢。

    運維管理操作不做啟動預留預檢（避免 admin 重啟 backend/整合容器誤 402）。
    運行時長仍經 ``on_docker_started`` + ``settle_tick`` 對已 assign_owner 的服務計費。
    臨時任務容器將來應呼叫 ``preflight_billable_container_run``。
    """
    if not billing_enabled():
        return
    _ = service


def preflight_billable_container_run(service: str) -> None:
    """可計費容器（如臨時任務 run）啟動前預檢積分。"""
    if not billing_enabled():
        return
    user = resolve_docker_user()
    get_docker_billing_tracker().ensure_can_start(service, user_id=user)


def on_docker_started(service: str) -> dict[str, Any]:
    user = resolve_docker_user()
    tracker = get_docker_billing_tracker()
    tracker.assign_owner(service, user)
    return {"owner": user, "service": service}


def on_docker_stopped(service: str) -> dict[str, Any]:
    user = resolve_docker_user()
    tracker = get_docker_billing_tracker()
    charge = tracker.on_stop(service, user_id=user)
    return {"owner": user, "service": service, "final_charge": charge}


def docker_billing_for_request() -> dict[str, Any]:
    user = resolve_docker_user() if gate_enabled() or True else default_anonymous_user()
    return get_docker_billing_tracker().summary(user_id=user)
