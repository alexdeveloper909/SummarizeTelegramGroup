ALTER TABLE collection_runs ADD COLUMN target_mode TEXT;

ALTER TABLE collection_runs ADD COLUMN forum_topic_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE collection_runs ADD COLUMN forum_active_topic_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE raw_messages ADD COLUMN forum_topic_id INTEGER;

ALTER TABLE raw_messages ADD COLUMN forum_topic_top_message_id INTEGER;

ALTER TABLE raw_messages ADD COLUMN reply_to_top_message_id INTEGER;

ALTER TABLE raw_messages ADD COLUMN is_forum_topic_message INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_raw_messages_run_topic
ON raw_messages (run_id, forum_topic_id, telegram_message_id);

CREATE TABLE IF NOT EXISTS run_forum_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    forum_topic_id INTEGER NOT NULL,
    forum_topic_title TEXT NOT NULL,
    forum_topic_top_message_id INTEGER NOT NULL,
    forum_topic_date TEXT NOT NULL,
    unread_count INTEGER NOT NULL DEFAULT 0,
    unread_mentions_count INTEGER NOT NULL DEFAULT 0,
    unread_reactions_count INTEGER NOT NULL DEFAULT 0,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    is_closed INTEGER NOT NULL DEFAULT 0,
    is_hidden INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (target_id) REFERENCES report_targets (id),
    UNIQUE (run_id, forum_topic_id)
);

CREATE INDEX IF NOT EXISTS idx_run_forum_topics_run_id
ON run_forum_topics (run_id);
