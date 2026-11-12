"""CloudAlerts — 雲資源告警系統（自 cloud_console 抽出）。"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import logger

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
                # 套件化後多一層目錄：parents[3] 仍指向 repo 根，維持原 backend/data/cloud_alerts。
                str(Path(__file__).resolve().parents[3] / "backend" / "data" / "cloud_alerts"),
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
