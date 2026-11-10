"""Docker 容器管理與雲控制台 API。

自 backend.main 抽出；端點行為、模型與回應結構不變。全域公司預算狀態改讀
`backend.services.company_budget`（已自 main 抽出）。
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.billing.docker_api import (
    docker_billing_for_request,
    on_docker_started,
    on_docker_stopped,
    preflight_docker_start,
)
from backend.billing.errors import InsufficientCreditsError
from backend.company.docker_tools import DOCKER_SERVICE_HOURLY_RATES, get_service_hourly_rate
from backend.services.aliyun_bss import get_aliyun_bss
from backend.services.cloud_console import (
    get_cloud_alerts,
    get_cloud_billing,
    get_cloud_events,
    get_cloud_monitor,
)
from backend.services.company_budget import get_company_budget_state
from backend.services.docker_manager import get_docker_manager

router = APIRouter(tags=["docker-cloud"])


# ==================== Docker 容器管理 API ====================

@router.get("/docker/status")
async def docker_status():
    """獲取 Docker 容器狀態摘要（含按時計費費率）。"""
    dm = get_docker_manager()
    return {
        "available": dm.available,
        "containers": dm.list_containers(),
        "health": dm.health_check() if dm.available else {"_error": "Docker 不可用"},
        "hourly_rates": DOCKER_SERVICE_HOURLY_RATES,
    }


@router.get("/docker/budget")
async def docker_budget():
    """獲取 Docker 容器預算狀態（公司全權控制）。

    返回當前 Docker 成本、預算壓力、優化建議和自動優化記錄。
    """
    dm = get_docker_manager()

    # 計算當前容器運行成本
    services: list[dict[str, Any]] = []
    total_docker_cost = 0.0
    total_hourly_rate = 0.0

    if dm.available:
        for c in dm.list_containers():
            svc = c.get("service", c["name"])
            if svc == "_docker_unavailable":
                continue
            if svc not in DOCKER_SERVICE_HOURLY_RATES:
                continue
            rate = get_service_hourly_rate(svc)
            uptime_s = float(c.get("uptime_seconds", 0))
            hours = uptime_s / 3600.0
            cost = rate * hours
            is_running = c.get("status", "").startswith("Up")
            services.append({
                "service": svc,
                "rate_per_hour": rate,
                "uptime_hours": round(hours, 2),
                "cost": round(cost, 4),
                "status": "running" if is_running else "stopped",
            })
            if is_running:
                total_docker_cost += cost
                total_hourly_rate += rate

    return {
        "available": dm.available,
        "services": services,
        "total_docker_cost": round(total_docker_cost, 4),
        "total_hourly_rate": round(total_hourly_rate, 4),
        "monthly_projection": round(total_hourly_rate * 24 * 30, 4),
        "company_budget": get_company_budget_state(),
        "user_billing": docker_billing_for_request(),
    }


@router.get("/docker/containers")
async def docker_containers():
    """列出所有容器。"""
    dm = get_docker_manager()
    return {"containers": dm.list_containers()}


@router.get("/docker/logs/{service}")
async def docker_logs(service: str, tail: int = 100):
    """獲取指定服務的日誌。"""
    dm = get_docker_manager()
    logs = dm.get_container_logs(service, tail=tail)
    return {"service": service, "tail": tail, "logs": logs}


@router.get("/docker/stats")
async def docker_stats():
    """獲取容器資源使用統計（含主機 CPU/記憶體/磁碟總覽）。"""
    dm = get_docker_manager()
    return {"stats": dm.get_stats(), "host": await asyncio.to_thread(dm.host_stats)}


@router.get("/system/resources")
async def system_resources():
    """主機 CPU／記憶體／網路吞吐。不查容器，供總覽環使用。"""
    dm = get_docker_manager()
    return await asyncio.to_thread(dm.host_stats)


@router.get("/docker/health")
async def docker_health():
    """檢查所有服務健康狀態。"""
    dm = get_docker_manager()
    return dm.health_check()


@router.post("/docker/restart/{service}")
async def docker_restart(service: str):
    """重啟指定服務。"""
    try:
        preflight_docker_start(service)
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=exc.message) from exc
    dm = get_docker_manager()
    on_docker_stopped(service)
    result = dm.restart_service(service)
    if result.get("success"):
        result["billing"] = on_docker_started(service)
    return result


@router.post("/docker/stop/{service}")
async def docker_stop(service: str):
    """停止指定服務。"""
    dm = get_docker_manager()
    result = dm.stop_service(service)
    if result.get("success"):
        result["billing"] = on_docker_stopped(service)
    return result


@router.post("/docker/start/{service}")
async def docker_start(service: str):
    """啟動指定服務。"""
    try:
        preflight_docker_start(service)
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=exc.message) from exc
    dm = get_docker_manager()
    result = dm.start_service(service)
    if result.get("success"):
        result["billing"] = on_docker_started(service)
    return result


# ==================== 雲控制台 API ====================


@router.get("/cloud/billing")
async def cloud_billing():
    """獲取雲端費用摘要（Docker 按時計費 + 阿里雲 BSS）。"""
    billing = get_cloud_billing()
    return billing.get_billing_summary()


@router.get("/cloud/aliyun")
async def cloud_aliyun_status():
    """阿里雲 BSS 接入狀態與本月帳目。"""
    return get_aliyun_bss().get_billing_overview(force=True)


@router.get("/cloud/monitoring")
async def cloud_monitoring(range: str = "1h"):
    """獲取資源監控歷史數據。

    Args:
        range: 時間範圍（1h / 6h / 24h）
    """
    range_map = {"1h": 1.0, "6h": 6.0, "24h": 24.0}
    hours = range_map.get(range, 1.0)
    monitor = get_cloud_monitor()
    return monitor.get_history(hours)


@router.get("/cloud/monitoring/latest")
async def cloud_monitoring_latest():
    """獲取最新資源快照。"""
    monitor = get_cloud_monitor()
    data = monitor.get_latest()
    if data is None:
        return {"services": {}, "ts": None}
    return data


@router.get("/cloud/events")
async def cloud_events(limit: int = 50):
    """獲取容器事件時間線。"""
    events = get_cloud_events()
    return {"events": events.get_events(limit)}


@router.get("/cloud/alerts")
async def cloud_alerts_list():
    """獲取告警規則列表。"""
    alerts = get_cloud_alerts()
    return {
        "rules": alerts.list_rules(),
        "history": alerts.get_alert_history(50),
    }


class AlertRuleCreate(BaseModel):
    name: str
    metric: str  # cpu / memory
    threshold: float
    service: str = "*"


@router.post("/cloud/alerts")
async def cloud_alerts_create(rule: AlertRuleCreate):
    """創建告警規則。"""
    alerts = get_cloud_alerts()
    return alerts.create_rule(
        name=rule.name,
        metric=rule.metric,
        threshold=rule.threshold,
        service=rule.service,
    )


@router.post("/cloud/alerts/{rule_id}/toggle")
async def cloud_alerts_toggle(rule_id: str):
    """切換告警規則啟用狀態。"""
    alerts = get_cloud_alerts()
    result = alerts.toggle_rule(rule_id)
    if result is None:
        raise HTTPException(status_code=404, detail="規則不存在")
    return result


@router.delete("/cloud/alerts/{rule_id}")
async def cloud_alerts_delete(rule_id: str):
    """刪除告警規則。"""
    alerts = get_cloud_alerts()
    if not alerts.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="規則不存在")
    return {"deleted": True}
