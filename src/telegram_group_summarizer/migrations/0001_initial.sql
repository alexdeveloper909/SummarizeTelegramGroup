CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_key TEXT NOT NULL UNIQUE,
    telegram_entity_id INTEGER,
    telegram_entity_type TEXT,
    display_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    target_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    mode TEXT,
    lookback_hours INTEGER NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    resolved_entity_id INTEGER,
    resolved_entity_type TEXT,
    resolved_entity_display_name TEXT,
    report_output_path TEXT,
    read_marked_at TEXT,
    raw_purged_at TEXT,
    FOREIGN KEY (target_id) REFERENCES report_targets (id)
);

CREATE TABLE IF NOT EXISTS raw_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    message_timestamp TEXT NOT NULL,
    sender_id INTEGER,
    sender_name TEXT,
    text_content TEXT NOT NULL,
    reply_to_message_id INTEGER,
    forward_source TEXT,
    has_links INTEGER NOT NULL DEFAULT 0,
    has_media INTEGER NOT NULL DEFAULT 0,
    media_kind TEXT,
    edited_at TEXT,
    is_service_message INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (target_id) REFERENCES report_targets (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_messages_run_message
ON raw_messages (run_id, telegram_message_id);

CREATE INDEX IF NOT EXISTS idx_raw_messages_target_timestamp
ON raw_messages (target_id, message_timestamp);

CREATE INDEX IF NOT EXISTS idx_raw_messages_run_id
ON raw_messages (run_id);

CREATE TABLE IF NOT EXISTS generated_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    target_id INTEGER NOT NULL,
    report_markdown TEXT NOT NULL,
    output_path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (target_id) REFERENCES report_targets (id)
);
