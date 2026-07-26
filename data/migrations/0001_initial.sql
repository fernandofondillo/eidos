-- EIDOS migration 0001 — Initial schema for the 5-layer cognitive memory.
-- Applied at first run by eidos.utils.migrations.
-- All tables live in the single portable file data/eidos.db.

-- ============================================================================
-- Capa 1 — Sensorial / Working memory
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensory_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,                -- ISO-8601 UTC
    kind        TEXT    NOT NULL,                -- 'user_input' | 'response' | 'system' | 'tool'
    content     TEXT    NOT NULL,
    metadata    TEXT    DEFAULT '{}'             -- JSON blob
);
CREATE INDEX IF NOT EXISTS idx_sensory_ts ON sensory_events(ts DESC);

-- ============================================================================
-- Capa 2 — Episodic memory (Hipocampo)
-- sqlite-vec virtual table created lazily on first connection (see episodic.py)
-- because the vec0 extension must be loaded before CREATE VIRTUAL TABLE.
-- ============================================================================
CREATE TABLE IF NOT EXISTS episodic_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL,
    kind         TEXT    NOT NULL,               -- 'interaction' | 'observation' | 'decision'
    content      TEXT    NOT NULL,
    embedding    TEXT    DEFAULT NULL,           -- JSON list[float] (cached for inspection)
    importance   REAL    NOT NULL DEFAULT 0.5,   -- [0,1] used for LRU pruning
    metadata     TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_episodic_ts        ON episodic_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_events(importance DESC);

-- ============================================================================
-- Capa 4 — Procedural memory (Cerebelo) — capsule registry
-- The .eidos file itself lives in data/capsules/<id>.eidos; this table is the index.
-- ============================================================================
CREATE TABLE IF NOT EXISTS capsules (
    id              TEXT    PRIMARY KEY,         -- UUID v4
    name            TEXT    NOT NULL,
    version         TEXT    NOT NULL,
    description     TEXT    DEFAULT '',
    file_path       TEXT    NOT NULL,            -- relative to project root
    created_at      TEXT    NOT NULL,
    ttl_days        INTEGER NOT NULL DEFAULT 7,
    uses            INTEGER NOT NULL DEFAULT 0,
    last_used       TEXT,
    favorite        INTEGER NOT NULL DEFAULT 0,  -- 0/1 boolean
    genesis_confidence REAL  DEFAULT NULL,
    parent_capsule_id   TEXT DEFAULT NULL,
    metadata        TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_capsules_favorite ON capsules(favorite);
CREATE INDEX IF NOT EXISTS idx_capsules_last_used ON capsules(last_used);

-- ============================================================================
-- Capa 5 — Metacognitive memory (Lóbulo Frontal)
-- Indexes monologue JSON files in data/monologues/ for "why did I decide X?"
-- ============================================================================
CREATE TABLE IF NOT EXISTS monologue_index (
    id              TEXT    PRIMARY KEY,         -- matches Monologue.id (UUID v4)
    ts              TEXT    NOT NULL,
    input_summary   TEXT    NOT NULL,
    hypothesis      TEXT    NOT NULL,
    plan            TEXT    NOT NULL,            -- JSON list[str]
    risk            TEXT    NOT NULL,
    confidence      REAL    NOT NULL,
    backend         TEXT    NOT NULL,
    file_path       TEXT    NOT NULL,            -- relative to project root
    outcome         TEXT    DEFAULT NULL,        -- filled later by consolidator (Fase 1.3)
    route_type      TEXT    DEFAULT NULL         -- filled later by engine
);
CREATE INDEX IF NOT EXISTS idx_monologue_ts        ON monologue_index(ts DESC);
CREATE INDEX IF NOT EXISTS idx_monologue_confidence ON monologue_index(confidence);
CREATE INDEX IF NOT EXISTS idx_monologue_route     ON monologue_index(route_type);

-- ============================================================================
-- Migrations bookkeeping
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL
);
INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
