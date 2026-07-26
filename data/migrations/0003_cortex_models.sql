-- EIDOS migration 0003 — Fase 2: Cortex Hub bookkeeping.
-- Tracks downloaded models (GGUF/ONNX) in the local models/ directory.

CREATE TABLE IF NOT EXISTS models (
    id              TEXT    PRIMARY KEY,             -- e.g. "qwen2.5-3b-instruct-q4_k_m"
    name            TEXT    NOT NULL,
    filename        TEXT    NOT NULL,                -- relative to models_dir
    url             TEXT    NOT NULL,                -- download source
    sha256          TEXT,                             -- checksum (nullable until verified)
    size_bytes      INTEGER,
    format          TEXT    NOT NULL,                -- 'gguf' | 'onnx'
    quantization    TEXT,                             -- 'Q4_K_M', 'Q5_K_M', 'F16', etc.
    purpose         TEXT    NOT NULL,                -- 'monologue' | 'embedding' | 'vision'
    status          TEXT    NOT NULL DEFAULT 'absent', -- 'absent' | 'downloading' | 'ready' | 'corrupt'
    downloaded_at   TEXT,
    metadata        TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_models_status  ON models(status);
CREATE INDEX IF NOT EXISTS idx_models_purpose ON models(purpose);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (3, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
