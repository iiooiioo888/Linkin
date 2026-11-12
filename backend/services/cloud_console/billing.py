"""CloudBilling — 雲端費用計算（Docker 執行時長＋阿里雲 BSS；自 cloud_console 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.company.docker_tools import get_service_hourly_rate
from backend.services.aliyun_bss import get_aliyun_bss
from backend.services.docker_manager import DockerManager, get_docker_manager

# ═══════════════════════════════════════════════════════════════
# CloudBilling — 費用計算
# ═══════════════════════════════════════════════════════════════


class CloudBilling:
    """雲端費用計算器。

    合併兩類雲資源用量：
    - 本地 Docker：運行時長 × 小時費率（USD）
    - 阿里雲 BSS：帳號帳單總覽（CNY→USD）

    Agent 日預算應同時計入 API（LLM）與本模組回報的雲資源費用。
    """

    def __init__(self, docker: DockerManager | None = None) -> None:
        self._docker = docker or get_docker_manager()

    def get_docker_costs(self) -> dict[str, Any]:
        """僅本地容器費用。"""
        containers = self._docker.list_containers()
        realtime: dict[str, float] = {}
        per_service: list[dict[str, Any]] = []
        total_now = 0.0
        total_hourly = 0.0

        for c in containers:
            svc = c.get("service", c["name"])
            if svc == "_docker_unavailable":
                continue
            rate = get_service_hourly_rate(svc)
            uptime_s = float(c.get("uptime_seconds", 0))
            hours = uptime_s / 3600.0
            cost = rate * hours
            running = str(c.get("status", "")).startswith("Up")

            realtime[svc] = round(cost, 4)
            total_now += cost
            if running:
                total_hourly += rate
            per_service.append({
                "service": svc,
                "rate": rate,
                "uptime_hours": round(hours, 2),
                "cost": round(cost, 4),
                "source": "docker",
            })

        per_service.sort(key=lambda x: x["cost"], reverse=True)
        return {
            "realtime": realtime,
            "per_service": per_service,
            "total_now": round(total_now, 4),
            "total_hourly_rate": round(total_hourly, 4),
            "month_projected": round(total_hourly * 24 * 30, 4),
        }

    def get_billing_summary(self) -> dict[str, Any]:
        """獲取費用摘要（Docker + 阿里雲）。

        Returns:
            {
                "realtime": {service: cost},
                "per_service": [...],
                "today_total": float,            # Docker 今日 + 阿里雲今日粗估（USD）
                "month_total": float,            # Docker + 阿里雲本月（USD）
                "month_projected": float,
                "total_now": float,
                "docker": {...},
                "aliyun": {...},
                "breakdown": {api 由 Agent 側另計, docker, aliyun, cloud_total},
            }
        """
        docker = self.get_docker_costs()
        aliyun = get_aliyun_bss().get_billing_overview()

        per_service = list(docker["per_service"])
        for prod in aliyun.get("products") or []:
            per_service.append({
                "service": f"aliyun:{prod.get('product_code') or 'cloud'}",
                "rate": 0.0,
                "uptime_hours": 0.0,
                "cost": float(prod.get("cost_usd") or 0),
                "source": "aliyun",
                "product_name": prod.get("product_name"),
                "pretax_amount_cny": prod.get("pretax_amount_cny"),
            })
        per_service.sort(key=lambda x: x["cost"], reverse=True)

        aliyun_month = float(aliyun.get("month_total_usd") or 0)
        aliyun_today = float(aliyun.get("today_total_usd") or 0)
        docker_now = float(docker["total_now"])
        cloud_total = round(docker_now + aliyun_month, 4)

        realtime = dict(docker["realtime"])
        realtime["aliyun"] = round(aliyun_month, 4)

        return {
            "realtime": realtime,
            "per_service": per_service,
            "today_total": round(docker_now + aliyun_today, 4),
            "month_total": cloud_total,
            "month_projected": round(
                float(docker["month_projected"]) + aliyun_month, 4
            ),
            "total_now": cloud_total,
            "docker": docker,
            "aliyun": aliyun,
            "breakdown": {
                "docker_usd": docker_now,
                "aliyun_usd": aliyun_month,
                "cloud_total_usd": cloud_total,
            },
        }
