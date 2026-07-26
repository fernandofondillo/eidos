-- EIDOS migration 0004 — Fase 3: Génesis de cápsulas.
-- Tracks capsule drafts pending human approval and capsule genealogy.

-- Drafts generados por CapsuleForge que requieren aprobación humana.
-- Tras aprobación se mueven a la tabla 'capsules' (Fase 1.2).
CREATE TABLE IF NOT EXISTS capsule_drafts (
    id                  TEXT    PRIMARY KEY,             -- UUID v4
    requested_by        TEXT    NOT NULL,                -- 'user' | 'auto_evolution'
    request_input       TEXT    NOT NULL,                -- petición NL original
    name                TEXT    NOT NULL,
    version             TEXT    NOT NULL,
    description         TEXT    DEFAULT '',
    ontology            TEXT    DEFAULT '{}',            -- JSON
    rules               TEXT    DEFAULT '[]',            -- JSON array
    tone                TEXT    DEFAULT '{}',            -- JSON
    tools               TEXT    DEFAULT '[]',            -- JSON array (may be empty)
    genesis_confidence  REAL    NOT NULL,
    smoke_test_passed   INTEGER NOT NULL DEFAULT 0,      -- 0/1
    smoke_test_output   TEXT    DEFAULT NULL,            -- stderr/stdout resumido
    status              TEXT    NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected' | 'auto_approved'
    created_at          TEXT    NOT NULL,
    decided_at          TEXT    DEFAULT NULL,
    parent_capsule_id   TEXT    DEFAULT NULL,
    metadata            TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON capsule_drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_created ON capsule_drafts(created_at DESC);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (4, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
