"""Monitor hub snapshot collector (REST + WebSocket)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.hub.monitor import collect_hub_monitor
from backend.services.agent_monitor import collect_agent_monitor
from backend.services.dashboard import collect_dashboard
from backend.services.llm_ops import collect_llm_ops
from backend.services.optimization_monitor import collect_optimization_monitor


def collect_monitor_hub() -> dict[str, Any]:
    """Aggregate one monitor snapshot for WS push and GET /monitor/hub-snapshot."""
    agents = None
    optimization = None
    llm_ops = None
    hub = None
    dashboard = None
    billing = None
    errors: list[str] = []

    try:
        agents = collect_agent_monitor()
    except Exception as exc:
        errors.append(f"agents:{exc}")
    try:
        optimization = collect_optimization_monitor()
    except Exception as exc:
        errors.append(f"optimization:{exc}")
    try:
        llm_ops = collect_llm_ops()
    except Exception as exc:
        errors.append(f"llm_ops:{exc}")
    try:
        hub = collect_hub_monitor()
    except Exception as exc:
        errors.append(f"hub:{exc}")
    try:
        dashboard = collect_dashboard()
    except Exception as exc:
        errors.append(f"dashboard:{exc}")

    try:
        from backend.services.cloud_console import get_cloud_billing

        billing = get_cloud_billing().get_billing_summary()
    except Exception:
        billing = None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents": agents,
        "optimization": optimization,
        "llm_ops": llm_ops,
        "hub": hub,
        "dashboard": dashboard,
        "billing": billing,
        "errors": errors,
    }
