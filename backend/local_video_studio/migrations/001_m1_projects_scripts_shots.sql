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
