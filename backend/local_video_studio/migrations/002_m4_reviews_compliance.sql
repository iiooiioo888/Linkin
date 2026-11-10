-- M4–M5：審核與合規（create_all 亦會建表；此檔供 Postgres 手動對照）

CREATE TABLE IF NOT EXISTS lvs_reviews (
    id VARCHAR(36) PRIMARY KEY,
    asset_id VARCHAR(36) NOT NULL REFERENCES lvs_assets(id) ON DELETE CASCADE,
    decision VARCHAR(32) NOT NULL,
    reason TEXT,
    reviewer VARCHAR(128) NOT NULL DEFAULT 'owner',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_lvs_reviews_asset_id ON lvs_reviews (asset_id);

CREATE TABLE IF NOT EXISTS lvs_compliance_records (
    id VARCHAR(36) PRIMARY KEY,
    asset_id VARCHAR(36) NOT NULL REFERENCES lvs_assets(id) ON DELETE CASCADE,
    explicit_mark BOOLEAN NOT NULL DEFAULT TRUE,
    metadata_json JSON NOT NULL,
    watermark_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_lvs_compliance_asset_id ON lvs_compliance_records (asset_id);
