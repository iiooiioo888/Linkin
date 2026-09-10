"""雲控制台核心服務。

提供四大模組：
- CloudBilling: 費用計算（本地 Docker 按時計費 + 阿里雲 BSS 帳目）
- CloudMonitor: 資源監控（定期輪詢 Docker stats，內存存儲最近 24h）
- CloudAlerts: 告警系統（CPU/內存閾值規則，JSON 文件持久化）
- CloudEvents: 容器事件（操作時間線記錄）

所有服務透過 DockerManager 獲取底層數據，Docker 不可用時優雅降級。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.company.docker_tools import (
    get_service_hourly_rate,
)
from backend.services.aliyun_bss import get_aliyun_bss
from backend.services.docker_manager import DockerManager, get_docker_manager

logger = logging.getLogger(__name__)

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


# ═══════════════════════════════════════════════════════════════
# CloudMonitor — 資源監控
# ═══════════════════════════════════════════════════════════════


class CloudMonitor:
    """資源監控服務。

    定期輪詢 Docker stats，內存存儲最近 24 小時的歷史數據點。
    提供按時間範圍查詢的歷史數據接口。
    """

    # 數據點保留策略
    MAX_DATA_POINTS = 1440  # 24h × 60min
    POLL_INTERVAL_SECONDS = 60  # 每分鐘採集一次

    def __init__(self, docker: DockerManager | None = None) -> None:
        self._docker = docker or get_docker_manager()
        self._history: list[dict[str, Any]] = []  # [{ts, services: {svc: {cpu, mem, net}}}]
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """啟動後台監控線程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("CloudMonitor 後台監控已啟動（間隔 %ds）", self.POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        """停止後台監控線程。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("CloudMonitor 後台監控已停止")

    def _poll_loop(self) -> None:
        """後台輪詢迴圈。"""
        while self._running:
            try:
                self._collect()
            except Exception:
                logger.debug("CloudMonitor 採集異常", exc_info=True)
            time.sleep(self.POLL_INTERVAL_SECONDS)

    def _collect(self) -> None:
        """採集一次資源數據。"""
        if not self._docker.available:
            return

        stats = self._docker.get_stats()
        if not stats:
            return

        point: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "services": {},
        }

        for svc, s in stats.items():
            if "error" in s:
                continue
            point["services"][svc] = {
                "cpu": s.get("cpu_percent", 0),
                "mem_mb": round(s.get("memory_usage", 0) / (1024 * 1024), 1),
                "mem_limit_mb": round(s.get("memory_limit", 0) / (1024 * 1024), 1),
                "net_rx_mb": round(s.get("network_rx", 0) / (1024 * 1024), 2),
                "net_tx_mb": round(s.get("network_tx", 0) / (1024 * 1024), 2),
            }

        with self._lock:
            self._history.append(point)
            # 保持 MAX_DATA_POINTS 上限
            if len(self._history) > self.MAX_DATA_POINTS:
                self._history = self._history[-self.MAX_DATA_POINTS:]

    def get_history(self, range_hours: float = 1.0) -> dict[str, Any]:
        """獲取指定時間範圍的監控歷史數據。

        Args:
            range_hours: 查詢範圍（小時），預設最近 1 小時

        Returns:
            {
                "points": [{ts, services: {svc: {cpu, mem_mb, net_rx_mb, net_tx_mb}}}],
                "range_hours": float,
                "latest": {svc: {...}} | None,
            }
        """
        cutoff = time.time() - range_hours * 3600

        with self._lock:
            filtered = []
            for p in self._history:
                try:
                    pt = datetime.fromisoformat(p["ts"])
                    if pt.timestamp() >= cutoff:
                        filtered.append(p)
                except (ValueError, TypeError):
                    continue

            latest = filtered[-1] if filtered else None

        return {
            "points": filtered,
            "range_hours": range_hours,
            "latest": latest,
        }

    def get_latest(self) -> dict[str, Any] | None:
        """獲取最新一次採集數據。"""
        with self._lock:
            if not self._history:
                # 若無歷史數據，立即採集一次
                self._collect()
            return self._history[-1] if self._history else None


# ═══════════════════════════════════════════════════════════════
# CloudAlerts — 告警系統
# ═══════════════════════════════════════════════════════════════


class CloudAlerts:
    """告警系統。

    支援 CPU / 內存閾值告警規則，JSON 文件持久化。
    規則格式：{id, name, metric, threshold, service, enabled, created_at}
    """

    def __init__(self, data_dir: str | None = None) -> None:
        if data_dir is None:
            data_dir = os.getenv(
                "CLOUD_ALERTS_DIR",
                str(Path(__file__).resolve().parents[2] / "backend" / "data" / "cloud_alerts"),
            )
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._rules_file = self._data_dir / "alert_rules.json"
        self._history_file = self._data_dir / "alert_history.jsonl"
        self._rules: dict[str, dict[str, Any]] = {}
        self._load_rules()

    # ── 規則管理 ──

    def _load_rules(self) -> None:
        """從文件加載告警規則。"""
        try:
            if self._rules_file.exists():
                data = json.loads(self._rules_file.read_text(encoding="utf-8"))
                self._rules = {r["id"]: r for r in data}
        except Exception:
            logger.debug("加載告警規則失敗", exc_info=True)

    def _save_rules(self) -> None:
        """保存告警規則到文件。"""
        try:
            self._rules_file.write_text(
                json.dumps(list(self._rules.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("保存告警規則失敗", exc_info=True)

    def list_rules(self) -> list[dict[str, Any]]:
        """列出所有告警規則。"""
        return list(self._rules.values())

    def create_rule(self, name: str, metric: str, threshold: float, service: str = "*") -> dict[str, Any]:
        """創建告警規則。

        Args:
            name: 規則名稱
            metric: 監控指標（cpu / memory）
            threshold: 閾值（CPU 百分比 / 內存 MB）
            service: 目標服務（* 表示全部）

        Returns:
            創建的規則字典
        """
        rule = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "metric": metric,
            "threshold": threshold,
            "service": service,
            "enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rule_id = str(rule["id"])
        self._rules[rule_id] = rule
        self._save_rules()
        return rule

    def toggle_rule(self, rule_id: str) -> dict[str, Any] | None:
        """切換規則啟用狀態。"""
        rule = self._rules.get(rule_id)
        if rule is None:
            return None
        rule["enabled"] = not rule["enabled"]
        self._save_rules()
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        """刪除告警規則。"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._save_rules()
            return True
        return False

    # ── 告警檢查 ──

    def check_alerts(self, monitor_data: dict[str, Any]) -> list[dict[str, Any]]:
        """檢查最新監控數據是否觸發告警。

        Args:
            monitor_data: CloudMonitor.get_latest() 返回的數據點

        Returns:
            觸發的告警列表
        """
        triggered: list[dict[str, Any]] = []
        services = monitor_data.get("services", {})

        for rule in self._rules.values():
            if not rule.get("enabled", True):
                continue

            target_svc = rule.get("service", "*")
            metric = rule.get("metric", "cpu")
            threshold = rule.get("threshold", 0)

            for svc, data in services.items():
                if target_svc != "*" and target_svc != svc:
                    continue

                value = data.get("cpu" if metric == "cpu" else "mem_mb", 0)
                if value > threshold:
                    alert = {
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "service": svc,
                        "metric": metric,
                        "value": value,
                        "threshold": threshold,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                    triggered.append(alert)
                    self._record_alert(alert)

        return triggered

    def _record_alert(self, alert: dict[str, Any]) -> None:
        """記錄告警歷史。"""
        try:
            with open(self._history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("記錄告警歷史失敗", exc_info=True)

    def get_alert_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """獲取告警歷史記錄。"""
        if not self._history_file.exists():
            return []
        try:
            lines = self._history_file.read_text(encoding="utf-8").strip().split("\n")
            records = [json.loads(line) for line in lines if line.strip()]
            return records[-limit:]
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════
# CloudEvents — 容器事件
# ═══════════════════════════════════════════════════════════════


class CloudEvents:
    """容器事件記錄器。

    記錄容器 start/stop/restart 操作，形成操作時間線。
    """

    def __init__(self, data_dir: str | None = None) -> None:
        if data_dir is None:
            data_dir = os.getenv(
                "CLOUD_EVENTS_DIR",
                str(Path(__file__).resolve().parents[2] / "backend" / "data" / "cloud_events"),
            )
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._events_file = self._data_dir / "events.jsonl"

    def record(self, event_type: str, service: str, detail: str = "") -> None:
        """記錄容器事件。

        Args:
            event_type: 事件類型（restart / stop / start）
            service: 服務名稱
            detail: 詳細信息
        """
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "service": service,
            "detail": detail,
        }
        try:
            with open(self._events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("記錄容器事件失敗", exc_info=True)

    def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """獲取最近的容器事件。

        Args:
            limit: 返回數量

        Returns:
            事件列表（按時間倒序）
        """
        if not self._events_file.exists():
            return []
        try:
            lines = self._events_file.read_text(encoding="utf-8").strip().split("\n")
            records = [json.loads(line) for line in lines if line.strip()]
            records.sort(key=lambda x: x.get("ts", ""), reverse=True)
            return records[:limit]
        except Exception:
            return []


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