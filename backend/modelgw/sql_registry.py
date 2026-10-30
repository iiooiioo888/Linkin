"""SQL Registry（SQLite 過渡；Postgres 權威目標）。

實作 ``Registry`` Protocol；``get(model_id)`` 簽名不變，tenant 以預設 ``""`` 解析。
技術債：本波以 SQLite 檔＋WAL 滿足多進程同一真相；權威目標仍為 Postgres。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from backend.modelgw.registry import ModelRecord, ModelStatus

_SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "001_modelgw_schema.sql"

_DEFAULT_TENANT = ""

_STATUS_VALUES = {s.value for s in ModelStatus}


def _bool_int(v: Any) -> int:
    return 1 if bool(v) else 0


def parse_database_url(url: str) -> tuple[str, str]:
    """回傳 (engine, path_or_dsn)。

    支援：
    - ``sqlite:////abs/path.db``／``sqlite:///rel.db``／``sqlite:///:memory:``
    - 純檔案路徑（視為 sqlite）
    - ``postgresql://...``／``postgres://...``（本波未實作連線；呼叫端應拒）
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("空 DATABASE_URL")
    lower = raw.lower()
    if lower.startswith(("postgres://", "postgresql://")):
        return "postgres", raw
    if lower.startswith("sqlite:"):
        # sqlite:///path → path；sqlite:////abs → /abs；sqlite:///:memory: → :memory:
        rest = raw.split(":", 1)[1]
        if rest.startswith("////"):
            path = "/" + rest[4:]
        elif rest.startswith("///"):
            path = rest[3:]
        else:
            path = rest.lstrip("/")
        if path in {"", ":memory:"} or path == "/:memory:":
            return "sqlite", ":memory:"
        return "sqlite", path
    # bare path
    return "sqlite", raw


class SqliteRegistry:
    """共享檔＋WAL 的 Registry；滿足 A1／A2（多連線同一真相）。"""

    def __init__(
        self,
        db_path: str,
        *,
        default_tenant: str = _DEFAULT_TENANT,
        ensure_schema: bool = True,
    ) -> None:
        self.db_path = db_path
        self.default_tenant = default_tenant
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path,
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,  # 手動交易
        )
        self._conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        if ensure_schema:
            self.ensure_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ensure_schema(self) -> None:
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._lock:
            self._conn.executescript(sql)

    def _tenant(self, tenant_id: str | None) -> str:
        if tenant_id is None:
            return self.default_tenant
        return tenant_id

    def get(self, model_id: str) -> ModelRecord | None:
        return self.get_for_tenant(self.default_tenant, model_id)

    def get_for_tenant(self, tenant_id: str, model_id: str) -> ModelRecord | None:
        tid = self._tenant(tenant_id)
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM modelgw_models WHERE tenant_id = ? AND model_id = ?",
                (tid, model_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def upsert(self, record: ModelRecord, *, tenant_id: str | None = None) -> None:
        """全量覆蓋寫入（測試／內部）；回調請走 ``apply_callback_upsert``。"""
        tid = self._tenant(tenant_id)
        self._upsert_record(tid, record, bump_version=True)

    def insert_if_absent(self, record: ModelRecord, *, tenant_id: str | None = None) -> bool:
        """冷啟動 seed：僅當列不存在時插入；已有回調列不覆蓋。回傳是否插入。"""
        tid = self._tenant(tenant_id)
        payload = self._record_params(tid, record)
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO modelgw_models (
                    tenant_id, model_id, revision, endpoint, runtime, provider,
                    gpu_type, lease_id, replicas, created_at, last_used_at, ttl,
                    status, license, trust_remote_code, gated, gated_approved,
                    checksum, plane, extras, updated_at, row_version
                ) VALUES (
                    :tenant_id, :model_id, :revision, :endpoint, :runtime, :provider,
                    :gpu_type, :lease_id, :replicas, :created_at, :last_used_at, :ttl,
                    :status, :license, :trust_remote_code, :gated, :gated_approved,
                    :checksum, :plane, :extras, datetime('now'), 1
                )
                """,
                payload,
            )
            return cur.rowcount > 0

    def seed_if_empty(self, records: list[ModelRecord], *, tenant_id: str | None = None) -> int:
        """對每列做 insert_if_absent；回傳新插入筆數。"""
        n = 0
        for rec in records:
            if self.insert_if_absent(rec, tenant_id=tenant_id):
                n += 1
        return n

    def ready(self) -> list[ModelRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM modelgw_models WHERE status = ? ORDER BY model_id",
                (ModelStatus.READY.value,),
            )
            rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def ready_ids(self) -> list[str]:
        return sorted(r.model_id for r in self.ready())

    def all(self) -> list[ModelRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM modelgw_models ORDER BY tenant_id, model_id"
            )
            rows = cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    def all_with_tenant(self) -> list[tuple[str, ModelRecord]]:
        """P3 poller：全表 (tenant_id, record)；預設 tenant_id=""。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM modelgw_models ORDER BY tenant_id, model_id"
            )
            rows = cur.fetchall()
        return [(str(r["tenant_id"]), self._row_to_record(r)) for r in rows]

    def row_version(self, model_id: str, *, tenant_id: str | None = None) -> int | None:
        tid = self._tenant(tenant_id)
        with self._lock:
            cur = self._conn.execute(
                "SELECT row_version FROM modelgw_models WHERE tenant_id = ? AND model_id = ?",
                (tid, model_id),
            )
            row = cur.fetchone()
        return int(row["row_version"]) if row else None

    def get_callback(
        self, idempotency_key: str, *, tenant_id: str | None = None
    ) -> dict[str, Any] | None:
        tid = self._tenant(tenant_id)
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT request_hash, response_snapshot, model_id, outcome_status
                FROM modelgw_deploy_callbacks
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tid, idempotency_key),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "request_hash": row["request_hash"],
            "response_snapshot": json.loads(row["response_snapshot"]),
            "model_id": row["model_id"],
            "outcome_status": row["outcome_status"],
        }

    def apply_deploy_write(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
        record: ModelRecord,
        response_snapshot: dict[str, Any],
        allow_create: bool = True,
        outcome: str = "",
    ) -> dict[str, Any]:
        """交易內：冪等檢查 → 狀態單調 → upsert model → 寫 callback 日誌。

        回傳 response_snapshot（含 idempotent_replay／row_version）。
        衝突時拋 ``CallbackConflict``。
        """
        from backend.modelgw.callback import CallbackConflict, assert_status_transition

        tid = self._tenant(tenant_id)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                cur = self._conn.execute(
                    """
                    SELECT request_hash, response_snapshot FROM modelgw_deploy_callbacks
                    WHERE tenant_id = ? AND idempotency_key = ?
                    """,
                    (tid, idempotency_key),
                )
                existing = cur.fetchone()
                if existing is not None:
                    if existing["request_hash"] == request_hash:
                        snap = json.loads(existing["response_snapshot"])
                        snap["idempotent_replay"] = True
                        self._conn.execute("COMMIT")
                        return snap
                    self._conn.execute("ROLLBACK")
                    raise CallbackConflict(
                        "同冪等鍵但請求內容不同",
                        code="IDEMPOTENCY_KEY_REUSED",
                    )

                cur = self._conn.execute(
                    "SELECT status, row_version FROM modelgw_models "
                    "WHERE tenant_id = ? AND model_id = ?",
                    (tid, record.model_id),
                )
                row = cur.fetchone()
                if row is None:
                    if not allow_create:
                        self._conn.execute("ROLLBACK")
                        raise CallbackConflict(
                            f"模型不存在：{record.model_id}",
                            code="MODEL_MISSING",
                            http_status=404,
                        )
                    new_version = 1
                else:
                    old_status = str(row["status"])
                    new_status = (
                        record.status.value
                        if isinstance(record.status, ModelStatus)
                        else str(record.status)
                    )
                    assert_status_transition(
                        old_status, new_status, outcome=outcome
                    )
                    new_version = int(row["row_version"]) + 1

                params = self._record_params(tid, record)
                params["row_version"] = new_version
                self._conn.execute(
                    """
                    INSERT INTO modelgw_models (
                        tenant_id, model_id, revision, endpoint, runtime, provider,
                        gpu_type, lease_id, replicas, created_at, last_used_at, ttl,
                        status, license, trust_remote_code, gated, gated_approved,
                        checksum, plane, extras, updated_at, row_version
                    ) VALUES (
                        :tenant_id, :model_id, :revision, :endpoint, :runtime, :provider,
                        :gpu_type, :lease_id, :replicas, :created_at, :last_used_at, :ttl,
                        :status, :license, :trust_remote_code, :gated, :gated_approved,
                        :checksum, :plane, :extras, datetime('now'), :row_version
                    )
                    ON CONFLICT(tenant_id, model_id) DO UPDATE SET
                        revision = excluded.revision,
                        endpoint = excluded.endpoint,
                        runtime = excluded.runtime,
                        provider = excluded.provider,
                        gpu_type = excluded.gpu_type,
                        lease_id = excluded.lease_id,
                        replicas = excluded.replicas,
                        last_used_at = excluded.last_used_at,
                        ttl = excluded.ttl,
                        status = excluded.status,
                        license = excluded.license,
                        trust_remote_code = excluded.trust_remote_code,
                        gated = excluded.gated,
                        gated_approved = excluded.gated_approved,
                        checksum = excluded.checksum,
                        plane = excluded.plane,
                        extras = excluded.extras,
                        updated_at = datetime('now'),
                        row_version = excluded.row_version
                    """,
                    params,
                )
                outcome = (
                    record.status.value
                    if isinstance(record.status, ModelStatus)
                    else str(record.status)
                )
                snap = dict(response_snapshot)
                snap["row_version"] = new_version
                snap["idempotent_replay"] = False
                self._conn.execute(
                    """
                    INSERT INTO modelgw_deploy_callbacks (
                        tenant_id, idempotency_key, request_hash,
                        response_snapshot, model_id, outcome_status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tid,
                        idempotency_key,
                        request_hash,
                        json.dumps(snap, ensure_ascii=False, separators=(",", ":")),
                        record.model_id,
                        outcome,
                    ),
                )
                self._conn.execute("COMMIT")
                return snap
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise

    def _upsert_record(
        self, tenant_id: str, record: ModelRecord, *, bump_version: bool
    ) -> None:
        params = self._record_params(tenant_id, record)
        with self._lock:
            if bump_version:
                cur = self._conn.execute(
                    "SELECT row_version FROM modelgw_models "
                    "WHERE tenant_id = ? AND model_id = ?",
                    (tenant_id, record.model_id),
                )
                row = cur.fetchone()
                params["row_version"] = (int(row["row_version"]) + 1) if row else 1
            else:
                params["row_version"] = 1
            self._conn.execute(
                """
                INSERT INTO modelgw_models (
                    tenant_id, model_id, revision, endpoint, runtime, provider,
                    gpu_type, lease_id, replicas, created_at, last_used_at, ttl,
                    status, license, trust_remote_code, gated, gated_approved,
                    checksum, plane, extras, updated_at, row_version
                ) VALUES (
                    :tenant_id, :model_id, :revision, :endpoint, :runtime, :provider,
                    :gpu_type, :lease_id, :replicas, :created_at, :last_used_at, :ttl,
                    :status, :license, :trust_remote_code, :gated, :gated_approved,
                    :checksum, :plane, :extras, datetime('now'), :row_version
                )
                ON CONFLICT(tenant_id, model_id) DO UPDATE SET
                    revision = excluded.revision,
                    endpoint = excluded.endpoint,
                    runtime = excluded.runtime,
                    provider = excluded.provider,
                    gpu_type = excluded.gpu_type,
                    lease_id = excluded.lease_id,
                    replicas = excluded.replicas,
                    last_used_at = excluded.last_used_at,
                    ttl = excluded.ttl,
                    status = excluded.status,
                    license = excluded.license,
                    trust_remote_code = excluded.trust_remote_code,
                    gated = excluded.gated,
                    gated_approved = excluded.gated_approved,
                    checksum = excluded.checksum,
                    plane = excluded.plane,
                    extras = excluded.extras,
                    updated_at = datetime('now'),
                    row_version = excluded.row_version
                """,
                params,
            )

    def _record_params(self, tenant_id: str, record: ModelRecord) -> dict[str, Any]:
        status = (
            record.status.value
            if isinstance(record.status, ModelStatus)
            else str(record.status)
        )
        created = float(record.created_at or 0.0)
        if created <= 0:
            created = time.time()
        return {
            "tenant_id": tenant_id,
            "model_id": record.model_id,
            "revision": record.revision,
            "endpoint": record.endpoint or "",
            "runtime": record.runtime or "cloud",
            "provider": record.provider or "cloud",
            "gpu_type": record.gpu_type or "",
            "lease_id": record.lease_id or "",
            "replicas": int(record.replicas or 1),
            "created_at": created,
            "last_used_at": float(record.last_used_at or 0.0),
            "ttl": record.ttl,
            "status": status,
            "license": record.license or "Apache-2.0",
            "trust_remote_code": _bool_int(record.trust_remote_code),
            "gated": _bool_int(record.gated),
            "gated_approved": _bool_int(record.gated_approved),
            "checksum": record.checksum,
            "plane": record.plane or "cloud",
            "extras": json.dumps(record.extras or {}, ensure_ascii=False),
        }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ModelRecord:
        extras_raw = row["extras"] or "{}"
        try:
            extras = json.loads(extras_raw) if isinstance(extras_raw, str) else dict(extras_raw)
        except json.JSONDecodeError:
            extras = {}
        return ModelRecord(
            model_id=row["model_id"],
            revision=row["revision"],
            endpoint=row["endpoint"] or "",
            runtime=row["runtime"] or "cloud",
            provider=row["provider"] or "cloud",
            gpu_type=row["gpu_type"] or "",
            lease_id=row["lease_id"] or "",
            replicas=int(row["replicas"] or 1),
            created_at=float(row["created_at"] or 0.0),
            last_used_at=float(row["last_used_at"] or 0.0),
            ttl=row["ttl"],
            status=ModelStatus(str(row["status"]).upper()),
            license=row["license"] or "Apache-2.0",
            trust_remote_code=bool(row["trust_remote_code"]),
            gated=bool(row["gated"]),
            gated_approved=bool(row["gated_approved"]),
            checksum=row["checksum"],
            plane=row["plane"] or "cloud",
            extras=extras if isinstance(extras, dict) else {},
        )


def build_sql_registry(database_url: str) -> SqliteRegistry:
    """依 DSN 建立 Registry；本波僅 SQLite，Postgres URL 明確報錯。"""
    engine, path = parse_database_url(database_url)
    if engine == "postgres":
        raise RuntimeError(
            "MODELGW_DATABASE_URL 指向 Postgres，但本波尚未掛 psycopg；"
            "請用 sqlite:////path/modelgw.sqlite3（技術債過渡）或 "
            "MODELGW_REGISTRY_BACKEND=memory"
        )
    return SqliteRegistry(path)




__all__ = [
    "SqliteRegistry",
    "build_sql_registry",
    "parse_database_url",
]
