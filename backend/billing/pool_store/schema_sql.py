"""積分池 SQLite DDL（_POOL_SCHEMA；由 schema.py 於初始化時執行）。"""


_POOL_SCHEMA = """
CREATE TABLE IF NOT EXISTS balances (
    account_id TEXT NOT NULL,
    pool_type TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, pool_type)
);

CREATE TABLE IF NOT EXISTS grants (
    grant_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    pool_type TEXT NOT NULL,
    amount REAL NOT NULL,
    remaining REAL NOT NULL,
    expires_at TEXT,
    source TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '',
    lock_days INTEGER,
    lock_multiplier REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor_configs (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    effective_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS billing_appeals (
    appeal_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    task_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT,
    resolved_by TEXT,
    resolution_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_configs (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    effective_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_policies (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    effective_at TEXT NOT NULL,
    monthly_rollover_ratio REAL NOT NULL DEFAULT 0.5,
    rollover_cap REAL NOT NULL DEFAULT 50000,
    by_tier_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_config_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    operator TEXT NOT NULL,
    action TEXT NOT NULL,
    old_json TEXT,
    new_json TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rollover_records (
    record_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    month_key TEXT NOT NULL,
    unused_monthly REAL NOT NULL,
    rollover_ratio REAL NOT NULL,
    rolled_to_purchased REAL NOT NULL,
    forfeited REAL NOT NULL,
    policy_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(account_id, month_key)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    estimate_credits REAL NOT NULL DEFAULT 0,
    reserved_credits REAL NOT NULL DEFAULT 0,
    settled_credits REAL NOT NULL DEFAULT 0,
    pricing_config_version INTEGER,
    credit_policy_version INTEGER,
    rollover_policy_version INTEGER,
    pricing_snapshot_json TEXT,
    run_mode TEXT NOT NULL DEFAULT 'normal',
    lock_multiplier REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_key_binding (
    task_id TEXT PRIMARY KEY,
    key_id TEXT NOT NULL,
    org_id TEXT,
    binding_reason TEXT NOT NULL DEFAULT 'single_key',
    is_failover INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_ledger (
    entry_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    pool_type TEXT,
    amount REAL NOT NULL,
    balance_after REAL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_usage_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT,
    account_id TEXT NOT NULL,
    key_id TEXT,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_credits REAL NOT NULL DEFAULT 0,
    pricing_version INTEGER,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_reservations (
    reservation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'held',
    created_at TEXT NOT NULL,
    released_at TEXT
);

CREATE TABLE IF NOT EXISTS pool_ledger (
    entry_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    pool_type TEXT,
    source TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    task_id TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contributors (
    contributor_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    contributor_id TEXT,
    org_id TEXT,
    encrypted_key TEXT NOT NULL,
    limits_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    kyc_status TEXT NOT NULL DEFAULT 'none',
    kyc_level INTEGER NOT NULL DEFAULT 0,
    kyc_meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_health (
    key_id TEXT PRIMARY KEY,
    contributor_id TEXT,
    health_score REAL NOT NULL DEFAULT 1.0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_failure_at TEXT,
    last_failure_reason TEXT,
    balance_exhausted_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'healthy',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtasks (
    subtask_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    parent_subtask_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    estimate_credits REAL NOT NULL DEFAULT 0,
    settled_credits REAL NOT NULL DEFAULT 0,
    key_id TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_prefixes (
    prefix_id TEXT PRIMARY KEY,
    account_id TEXT,
    key_id TEXT,
    prefix_hash TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    savings_credits REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_cache_profile (
    key_id TEXT PRIMARY KEY,
    cache_prefix_count INTEGER NOT NULL DEFAULT 0,
    total_hits INTEGER NOT NULL DEFAULT 0,
    affinity_score REAL NOT NULL DEFAULT 0,
    profile_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fault_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    account_id TEXT,
    task_id TEXT,
    installment_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lock_installments (
    installment_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    total_amount REAL NOT NULL,
    per_installment REAL NOT NULL,
    paid_installments INTEGER NOT NULL DEFAULT 0,
    lock_days INTEGER NOT NULL,
    lock_multiplier REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    next_due_at TEXT,
    key_id TEXT,
    interval_days INTEGER NOT NULL DEFAULT 30,
    forfeited_amount REAL NOT NULL DEFAULT 0,
    failure_reason TEXT,
    appeal_deadline TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contribution_decay_log (
    account_id TEXT PRIMARY KEY,
    last_decay_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT,
    l3_hits INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    savings_credits REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grants_account_pool ON grants(account_id, pool_type);
CREATE INDEX IF NOT EXISTS idx_pool_ledger_account ON pool_ledger(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_account ON tasks(account_id);
CREATE INDEX IF NOT EXISTS idx_pool_usage_task ON pool_usage_events(task_id);
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id);
CREATE INDEX IF NOT EXISTS idx_cache_prefixes_key ON cache_prefixes(key_id);
CREATE INDEX IF NOT EXISTS idx_lock_installments_account ON lock_installments(account_id, status);

CREATE TABLE IF NOT EXISTS fault_pool_ledger (
    entry_id TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    reason TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    account_id TEXT,
    task_id TEXT,
    installment_id TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fault_pool_alerts (
    alert_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    message_zh TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 0,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_runtime (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT,
    routing_mode TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_key_splits (
    task_id TEXT PRIMARY KEY,
    split_mode TEXT NOT NULL,
    keys_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_daily_usage (
    key_id TEXT NOT NULL,
    day_key TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    credits_used REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (key_id, day_key)
);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_task ON routing_decisions(task_id);
CREATE INDEX IF NOT EXISTS idx_fault_pool_ledger_created ON fault_pool_ledger(created_at);
"""
