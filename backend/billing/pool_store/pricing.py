"""PoolStore 的定價、積分政策與廠商配置讀取（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.billing.pricing_engine import DEFAULT_CREDIT_POLICY, DEFAULT_PRICING_CONFIG
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS

from .schema import _SchemaMixin


class _PricingMixin(_SchemaMixin):
    def active_pricing_config(self) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT version, config_json FROM pricing_configs
                   WHERE status='active' ORDER BY version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return {"version": 0, "config": DEFAULT_PRICING_CONFIG}
        return {"version": int(row["version"]), "config": json.loads(row["config_json"])}

    def active_credit_policy(self, plan_id: str = "free") -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT version, monthly_rollover_ratio, rollover_cap, by_tier_json
                   FROM credit_policies WHERE status='active' ORDER BY version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return {"version": 0, **DEFAULT_CREDIT_POLICY}
        by_tier = json.loads(row["by_tier_json"] or "{}")
        tier = by_tier.get(plan_id, {})
        ratio = float(tier.get("monthly_rollover_ratio", row["monthly_rollover_ratio"]))
        cap = float(tier.get("rollover_cap", row["rollover_cap"]))
        return {"version": int(row["version"]), "monthly_rollover_ratio": ratio, "rollover_cap": cap, "by_tier": by_tier}

    def active_vendor_config(self) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT version, config_json FROM vendor_configs
                   WHERE status='active' ORDER BY version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return {"version": 0, "config": DEFAULT_VENDOR_CONFIGS}
        return {"version": int(row["version"]), "config": json.loads(row["config_json"])}

    def snapshot_pricing(self, plan_id: str = "free") -> dict[str, Any]:
        pc = self.active_pricing_config()
        cp = self.active_credit_policy(plan_id)
        vc = self.active_vendor_config()
        merged = dict(pc["config"])
        merged["vendor_configs"] = vc["config"]
        return {
            "pricing_config_version": pc["version"],
            "credit_policy_version": cp["version"],
            "rollover_policy_version": cp["version"],
            "vendor_config_version": vc["version"],
            "pricing_config": merged,
            "credit_policy": cp,
        }

    def _policy_for_plan(self, conn: sqlite3.Connection, plan_id: str) -> dict[str, Any]:
        row = conn.execute(
            """SELECT version, monthly_rollover_ratio, rollover_cap, by_tier_json
               FROM credit_policies WHERE status='active' ORDER BY version DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return {"version": 0, **DEFAULT_CREDIT_POLICY}
        by_tier = json.loads(row["by_tier_json"] or "{}")
        tier = by_tier.get(plan_id, {})
        return {
            "version": int(row["version"]),
            "monthly_rollover_ratio": float(tier.get("monthly_rollover_ratio", row["monthly_rollover_ratio"])),
            "rollover_cap": float(tier.get("rollover_cap", row["rollover_cap"])),
        }
