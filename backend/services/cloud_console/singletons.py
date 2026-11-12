"""模組級單例與 get_cloud_* 取用函式（自 cloud_console 抽出）。"""

from __future__ import annotations

from .alerts import CloudAlerts
from .billing import CloudBilling
from .events import CloudEvents
from .monitor import CloudMonitor

# ═══════════════════════════════════════════════════════════════
# 模組級單例
# ═══════════════════════════════════════════════════════════════

_billing: CloudBilling | None = None
_monitor: CloudMonitor | None = None
_alerts: CloudAlerts | None = None
_events: CloudEvents | None = None


def get_cloud_billing() -> CloudBilling:
    global _billing
    if _billing is None:
        _billing = CloudBilling()
    return _billing


def get_cloud_monitor() -> CloudMonitor:
    global _monitor
    if _monitor is None:
        _monitor = CloudMonitor()
        _monitor.start()
    return _monitor


def get_cloud_alerts() -> CloudAlerts:
    global _alerts
    if _alerts is None:
        _alerts = CloudAlerts()
    return _alerts


def get_cloud_events() -> CloudEvents:
    global _events
    if _events is None:
        _events = CloudEvents()
    return _events
