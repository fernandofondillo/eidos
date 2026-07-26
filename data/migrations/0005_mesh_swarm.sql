-- EIDOS migration 0005 — Fase 4: EIDOS MESH.
-- Tracks discovered nodes and active resource tokens for the swarm.

-- Nodos EIDOS descubiertos en el bus local (registry del Leader).
CREATE TABLE IF NOT EXISTS mesh_nodes (
    id              TEXT    PRIMARY KEY,             -- UUID de la instancia
    pid             INTEGER NOT NULL,
    hostname        TEXT    NOT NULL,
    socket_path     TEXT    NOT NULL,               -- unix:// path
    role            TEXT    NOT NULL,                -- 'leader' | 'worker' | 'candidate'
    status          TEXT    NOT NULL DEFAULT 'alive', -- 'alive' | 'dead' | 'leaving'
    last_heartbeat  TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    metadata        TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_role ON mesh_nodes(role);
CREATE INDEX IF NOT EXISTS idx_mesh_nodes_status ON mesh_nodes(status);

-- Resource tokens activos (arbitraje del Leader).
CREATE TABLE IF NOT EXISTS resource_tokens (
    token_id        TEXT    PRIMARY KEY,             -- UUID del token
    resource        TEXT    NOT NULL,                -- 'cortex' | 'memory_write' | ...
    holder_node_id  TEXT    NOT NULL,
    acquired_at     TEXT    NOT NULL,
    expires_at      TEXT    NOT NULL,                -- TTL
    released_at     TEXT    DEFAULT NULL,
    metadata        TEXT    DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tokens_resource ON resource_tokens(resource);
CREATE INDEX IF NOT EXISTS idx_tokens_holder   ON resource_tokens(holder_node_id);
CREATE INDEX IF NOT EXISTS idx_tokens_expires  ON resource_tokens(expires_at);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (5, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
