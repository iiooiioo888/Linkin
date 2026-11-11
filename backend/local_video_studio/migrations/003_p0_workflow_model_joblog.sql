-- P0-03 / P0-11 / P0-12：workflow 版本、模型註冊、job 日誌欄位
-- SQLite／Postgres 兼容意圖稿；執行環境以 SQLAlchemy create_all 為準。

CREATE TABLE IF NOT EXISTS lvs_workflow_templates (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  json_path TEXT,
  mapping_path TEXT,
  workflow_json JSON NOT NULL,
  mapping_json JSON NOT NULL,
  required_models_json JSON,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS lvs_model_registry (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(255) NOT NULL UNIQUE,
  path TEXT NOT NULL,
  sha256 VARCHAR(64),
  vae_name VARCHAR(255),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 既有 SQLite 需手動 ALTER（create_all 不會改舊表）：
-- ALTER TABLE lvs_generation_jobs ADD COLUMN workflow_version INTEGER;
-- ALTER TABLE lvs_generation_jobs ADD COLUMN log_relative_path TEXT;
