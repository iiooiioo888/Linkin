"""Docker 計費 API 輔助（供 main.py 掛載 start/stop 前後處理）。"""

from __future__ import annotations

from typing import Any

from backend.auth.gate import gate_enabled
from backend.billing.context import current_billing_user, default_anonymous_user
from backend.billing.docker_meter import get_docker_billing_tracker


def resolve_docker_user() -> str:
    return current_billing_user() or default_anonymous_user()


def preflight_docker_start(service: str) -> None:
    """啟動/重啟前預檢積分；不足則拋 InsufficientCreditsError。"""
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
