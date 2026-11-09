-- M1 初始 schema（SQLite 友好；PostgreSQL 可將 JSON 改 JSONB、NUMERIC 保留）
-- 執行路徑：應用啟動時由 SQLAlchemy create_all 對齊；本檔供審計／手動遷移。

CREATE TABLE IF NOT EXISTS lvs_projects (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lvs_scripts (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(36) NOT NULL REFERENCES lvs_projects(id) ON DELETE CASCADE,
  content_json JSON NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_lvs_scripts_project_id ON lvs_scripts(project_id);

CREATE TABLE IF NOT EXISTS lvs_shots (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(36) NOT NULL REFERENCES lvs_projects(id) ON DELETE CASCADE,
  scene_no INTEGER NOT NULL,
  shot_no INTEGER NOT NULL,
  description TEXT NOT NULL,
  dialogue TEXT,
  duration_sec NUMERIC(6,2) NOT NULL DEFAULT 5,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  selected_keyframe_asset_id VARCHAR(36),
  selected_clip_asset_id VARCHAR(36),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_lvs_shot UNIQUE (project_id, scene_no, shot_no)
);

CREATE INDEX IF NOT EXISTS ix_lvs_shots_project_id ON lvs_shots(project_id);

CREATE TABLE IF NOT EXISTS lvs_schema_meta (
  key VARCHAR(64) PRIMARY KEY,
  value VARCHAR(64) NOT NULL
);

-- M2 tables (create_all 亦會建立)
CREATE TABLE IF NOT EXISTS lvs_generation_jobs (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(36) NOT NULL REFERENCES lvs_projects(id) ON DELETE CASCADE,
  shot_id VARCHAR(36) NOT NULL REFERENCES lvs_shots(id) ON DELETE CASCADE,
  job_type VARCHAR(32) NOT NULL,
  workflow_template VARCHAR(128) NOT NULL,
  params_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  priority INTEGER NOT NULL DEFAULT 100,
  data_class VARCHAR(32) NOT NULL DEFAULT 'local_only',
  assigned_agent VARCHAR(128),
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lvs_assets (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(36) NOT NULL REFERENCES lvs_projects(id) ON DELETE CASCADE,
  shot_id VARCHAR(36) REFERENCES lvs_shots(id) ON DELETE SET NULL,
  type VARCHAR(32) NOT NULL,
  relative_path TEXT NOT NULL,
  mime VARCHAR(128),
  bytes BIGINT,
  sha256 VARCHAR(64),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lvs_resource_records (
  id VARCHAR(36) PRIMARY KEY,
  job_id VARCHAR(36) NOT NULL REFERENCES lvs_generation_jobs(id) ON DELETE CASCADE,
  gpu_minutes NUMERIC(10,2),
  wall_minutes NUMERIC(10,2),
  attempts INTEGER,
  discarded_count INTEGER NOT NULL DEFAULT 0,
  storage_bytes BIGINT,
  api_calls INTEGER NOT NULL DEFAULT 0,
  electricity_note TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
