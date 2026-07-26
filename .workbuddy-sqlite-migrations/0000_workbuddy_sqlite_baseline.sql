CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    cwd TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    custom_title TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_activity_at INTEGER,
    deleted_at INTEGER,
    is_playground INTEGER NOT NULL DEFAULT 0,
    source_mode TEXT,
    is_background_automation INTEGER,
    mode TEXT,
    model TEXT,
    expert_id TEXT,
    expert_locale TEXT,
    expert_runtime_identity TEXT,
    expert_marketplace TEXT,
    permission_mode TEXT,
    use_sandbox_cli INTEGER,
    project_id TEXT
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS workspaces (
    path TEXT PRIMARY KEY,
    last_opened_at INTEGER NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'recurring',
    next_run_at INTEGER,
    last_run_at INTEGER,
    cwds TEXT NOT NULL DEFAULT '[]',
    rrule TEXT NOT NULL DEFAULT '',
    scheduled_at TEXT,
    valid_from TEXT,
    valid_until TEXT,
    model_id TEXT,
    model_is_thinking INTEGER NOT NULL DEFAULT 0,
    skills_json TEXT NOT NULL DEFAULT '[]',
    push_to_wechat INTEGER NOT NULL DEFAULT 0,
    push_to_wecom_bot INTEGER NOT NULL DEFAULT 0,
    owner_user_id TEXT,
    owner_status TEXT NOT NULL DEFAULT 'legacy_unassigned',
    owner_source TEXT,
    expert_id TEXT,
    expert_marketplace TEXT,
    connector_ids_json TEXT NOT NULL DEFAULT '[]',
    permission_mode TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted_at INTEGER
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_automations_owner
    ON automations(owner_user_id, owner_status, deleted_at);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS automation_runs (
    thread_id TEXT PRIMARY KEY,
    automation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    read_at INTEGER,
    thread_title TEXT,
    source_cwd TEXT,
    runs_json TEXT,
    result_success INTEGER,
    metadata_json TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS automation_runtime_state (
    automation_id TEXT PRIMARY KEY,
    last_run_at INTEGER,
    last_error TEXT,
    running INTEGER NOT NULL DEFAULT 0,
    running_started_at INTEGER,
    running_conversation_id TEXT,
    metadata_json TEXT
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS automation_delivery_outbox (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'wechatmp',
    automation_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    automation_name TEXT NOT NULL,
    owner_user_id TEXT,
    host_id TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_run_at INTEGER NOT NULL,
    lease_owner TEXT,
    lease_expire_at INTEGER,
    last_error_code TEXT,
    last_error_message TEXT,
    delivery_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    finished_at INTEGER
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS automation_delivery_outbox_dedupe_key_unique
    ON automation_delivery_outbox(dedupe_key);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_automation_delivery_outbox_status_next_run
    ON automation_delivery_outbox(status, next_run_at);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_automation_delivery_outbox_channel_status_next_run
    ON automation_delivery_outbox(channel, status, next_run_at);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_automation_delivery_outbox_run
    ON automation_delivery_outbox(automation_id, run_id);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_automation_delivery_outbox_owner_status
    ON automation_delivery_outbox(owner_user_id, status);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS idx_automation_delivery_outbox_supersede_lookup
    ON automation_delivery_outbox(automation_id, channel, owner_user_id, host_id, created_at);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS migration_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS session_usage (
    session_id TEXT PRIMARY KEY,
    used INTEGER NOT NULL,
    size INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    credit_json TEXT
);
