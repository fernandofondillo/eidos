-- EIDOS migration 0002 — Fase 1.3: Motivation + Consolidation bookkeeping.
-- Adds tables for reward events and consolidation runs.

-- Reward signal log — each reward contribution is auditable.
-- Drivers: 'curiosity' | 'capsule_reuse' | 'user_satisfaction'
CREATE TABLE IF NOT EXISTS reward_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    monologue_id    TEXT,                            -- may be NULL for non-monologue rewards
    driver          TEXT    NOT NULL,                -- 'curiosity' | 'capsule_reuse' | 'user_satisfaction'
    delta           REAL    NOT NULL,                -- contribution to reward [-1, 1]
    total           REAL    NOT NULL,                -- cumulative reward at this moment
    metadata        TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_reward_ts        ON reward_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_reward_driver    ON reward_events(driver);
CREATE INDEX IF NOT EXISTS idx_reward_monologue ON reward_events(monologue_id);

-- Consolidation runs log — for monitoring and debugging the background loop.
CREATE TABLE IF NOT EXISTS consolidation_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT    NOT NULL,
    kind                TEXT    NOT NULL,            -- 'full' | 'manual' | 'shutdown'
    items_processed     INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    details             TEXT    DEFAULT '{}'         -- JSON with per-step counts
);

UPDATE schema_migrations
SET applied_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE version = 1;

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
