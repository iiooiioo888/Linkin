"""PoolStore 的 API key 健康、路由決策、用量與貢獻者金鑰（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.billing.pool_types import POOL_CONTRIBUTION_LOCKED, POOL_CONTRIBUTION_UNLOCKED

from .schema import _utc_now
from .task_billing import _TaskBillingMixin


class _KeysMixin(_TaskBillingMixin):
    def save_task_key_split(self, task_id: str, keys: list[dict[str, Any]], *, split_mode: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_key_splits(task_id, split_mode, keys_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, split_mode, json.dumps(keys, ensure_ascii=False), _utc_now()),
            )

    def get_key_daily_usage(self, key_id: str, day_key: str | None = None) -> float:
        dk = day_key or datetime.now(timezone.utc).strftime("%Y%m%d")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT tokens_used FROM key_daily_usage WHERE key_id=? AND day_key=?",
                (key_id, dk),
            ).fetchone()
        return float(row["tokens_used"]) if row else 0.0

    def increment_key_usage(self, key_id: str, *, tokens: int = 0, credits: float = 0) -> None:
        dk = datetime.now(timezone.utc).strftime("%Y%m%d")
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO key_daily_usage(key_id, day_key, tokens_used, credits_used, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key_id, day_key) DO UPDATE SET
                   tokens_used = key_daily_usage.tokens_used + excluded.tokens_used,
                   credits_used = key_daily_usage.credits_used + excluded.credits_used,
                   updated_at = excluded.updated_at""",
                (key_id, dk, tokens, credits, now),
            )

    def get_key_concurrency(self, key_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS c FROM task_key_binding tkb
                   JOIN tasks t ON t.task_id = tkb.task_id
                   WHERE tkb.key_id=? AND t.status IN ('pending', 'running', 'active')""",
                (key_id,),
            ).fetchone()
        return int(row["c"] or 0) if row else 0

    def list_contributor_keys_with_health(self, account_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ak.key_id, ak.status, ak.limits_json, ak.org_id, ak.created_at,
                          kh.health_score, kh.status AS health_status, kh.failure_count,
                          kh.balance_exhausted_count, kh.last_failure_reason, kh.updated_at AS health_updated_at
                   FROM api_keys ak
                   JOIN contributors c ON c.contributor_id = ak.contributor_id
                   LEFT JOIN key_health kh ON kh.key_id = ak.key_id
                   WHERE c.account_id=? ORDER BY ak.created_at DESC""",
                (account_id.strip(),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            try:
                item["limits"] = json.loads(r["limits_json"] or "{}")
            except json.JSONDecodeError:
                item["limits"] = {}
            item.pop("limits_json", None)
            item["daily_usage"] = self.get_key_daily_usage(str(r["key_id"]))
            out.append(item)
        return out

    def _primary_contributor_key(self, account_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT ak.key_id FROM api_keys ak
                   JOIN contributors c ON c.contributor_id = ak.contributor_id
                   WHERE c.account_id=? AND ak.status='active'
                   ORDER BY ak.created_at DESC LIMIT 1""",
                (account_id.strip(),),
            ).fetchone()
        return str(row["key_id"]) if row else None

    def get_routing_runtime(self, key: str, default: Any = None) -> Any:
        with self._conn() as conn:
            row = conn.execute("SELECT value_json FROM routing_runtime WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError:
            return default

    def set_routing_runtime(self, key: str, value: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO routing_runtime(key, value_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at""",
                (key, json.dumps(value, ensure_ascii=False), _utc_now()),
            )

    def log_routing_decision(self, decision: dict[str, Any]) -> str:
        decision_id = f"rd_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO routing_decisions(decision_id, task_id, account_id, routing_mode, decision_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    decision_id,
                    decision.get("task_id", ""),
                    decision.get("account_id"),
                    decision.get("routing_mode", "single"),
                    json.dumps(decision, ensure_ascii=False),
                    _utc_now(),
                ),
            )
        return decision_id

    def get_routing_decision(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM routing_decisions WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["decision_json"])
        except json.JSONDecodeError:
            payload = {}
        return {"decision_id": row["decision_id"], **payload, "created_at": row["created_at"]}

    def resolve_contributor_account(self, key_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT c.account_id FROM api_keys ak
                   JOIN contributors c ON c.contributor_id = ak.contributor_id
                   WHERE ak.key_id=? AND ak.status='active' AND c.status='active'""",
                (key_id.strip(),),
            ).fetchone()
        return str(row["account_id"]) if row else None

    def ensure_contributor(self, account_id: str) -> str:
        cid = f"ctr_{account_id[:16]}"
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO contributors(contributor_id, account_id, status, created_at)
                   VALUES (?, ?, 'active', ?)""",
                (cid, account_id.strip(), now),
            )
        return cid

    def bind_contributor_key(
        self,
        account_id: str,
        encrypted_key: str,
        limits: dict | None = None,
        *,
        org_id: str | None = None,
        plaintext_key: str | None = None,
    ) -> dict[str, Any]:
        from backend.billing.key_crypto import encrypt_api_key

        cid = self.ensure_contributor(account_id)
        kid = f"key_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        limits_payload = dict(limits or {})
        if org_id:
            limits_payload.setdefault("org_id", org_id)
        raw = plaintext_key or encrypted_key
        if not raw.startswith("enc1:") and not raw.startswith("enc256:"):
            stored = encrypt_api_key(raw)
        else:
            stored = raw
        resolved_org = org_id or limits_payload.get("org_id")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO api_keys(key_id, contributor_id, org_id, encrypted_key, limits_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                (kid, cid, resolved_org, stored, json.dumps(limits_payload, ensure_ascii=False), now),
            )
            conn.execute(
                """INSERT OR IGNORE INTO key_health(key_id, contributor_id, health_score, status, updated_at)
                   VALUES (?, ?, 1.0, 'healthy', ?)""",
                (kid, cid, now),
            )
        return {
            "contributor_id": cid,
            "key_id": kid,
            "status": "active",
            "org_id": resolved_org,
            "limits": limits_payload,
            "encrypted": True,
        }

    def contributor_earnings(self, account_id: str) -> dict[str, Any]:
        bals = self.get_balances(account_id)
        with self._conn() as conn:
            keys = conn.execute(
                """SELECT key_id, status, created_at FROM api_keys
                   WHERE contributor_id IN (SELECT contributor_id FROM contributors WHERE account_id=?)""",
                (account_id.strip(),),
            ).fetchall()
        return {
            "contributor_id": f"ctr_{account_id[:16]}",
            "unlocked_earnings": float(bals.get(POOL_CONTRIBUTION_UNLOCKED, 0)),
            "locked_earnings": float(bals.get(POOL_CONTRIBUTION_LOCKED, 0)),
            "keys": [dict(k) for k in keys],
        }
