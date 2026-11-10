-- ModelGW P1/#130：獨立 modelgw_* 表（SQLite 過渡／Postgres 權威目標）
-- JSONB → TEXT（SQLite）；Postgres 可用 JSONB 替換 extras／response_snapshot。
-- 技術債：本波預設 SQLite 檔；權威目標仍為 Postgres。

CREATE TABLE IF NOT EXISTS modelgw_models (
    tenant_id TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    endpoint TEXT NOT NULL DEFAULT '',
    runtime TEXT NOT NULL DEFAULT 'cloud',
    provider TEXT NOT NULL DEFAULT 'cloud',
    gpu_type TEXT NOT NULL DEFAULT '',
    lease_id TEXT NOT NULL DEFAULT '',
    replicas INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL DEFAULT 0,
    last_used_at REAL NOT NULL DEFAULT 0,
    ttl REAL,
    status TEXT NOT NULL CHECK (
        status IN (
            'PENDING',
            'PROVISIONING',
            'DOWNLOADING',
            'LOADING',
            'READY',
            'FAILED',
            'TERMINATING'
        )
    ),
    license TEXT NOT NULL DEFAULT 'Apache-2.0',
    trust_remote_code INTEGER NOT NULL DEFAULT 0,
    gated INTEGER NOT NULL DEFAULT 0,
    gated_approved INTEGER NOT NULL DEFAULT 0,
    checksum TEXT,
    plane TEXT NOT NULL DEFAULT 'cloud',
    extras TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    row_version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (tenant_id, model_id)
);

CREATE INDEX IF NOT EXISTS idx_modelgw_models_status
    ON modelgw_models (status);

CREATE INDEX IF NOT EXISTS idx_modelgw_models_tenant_status
    ON modelgw_models (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_modelgw_models_ready
    ON modelgw_models (tenant_id, model_id)
    WHERE status = 'READY';

CREATE TABLE IF NOT EXISTS modelgw_deploy_callbacks (
    tenant_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_snapshot TEXT NOT NULL,
    model_id TEXT NOT NULL,
    outcome_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tenant_id, idempotency_key)
);
