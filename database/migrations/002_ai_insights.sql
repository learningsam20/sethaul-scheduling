-- On-demand AI insight generator snapshots

CREATE TABLE IF NOT EXISTS ai_insight_runs (
    run_id TEXT PRIMARY KEY,
    iso_week TEXT NOT NULL,
    model TEXT,
    insights_json TEXT NOT NULL,
    last_refreshed_at TEXT NOT NULL,
    actor_user_id TEXT,
    note TEXT
);

CREATE INDEX IF NOT EXISTS ix_ai_insight_runs_week
    ON ai_insight_runs(iso_week, last_refreshed_at DESC);
