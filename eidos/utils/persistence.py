"""Sistema de migraciones SQL versionadas para EIDOS.

Filosofía: cero dependencias (nada de Alembic). Las migraciones son
ficheros `.sql` numerados en `data/migrations/`, aplicados al arranque
de forma idempotente. El orden es estrictamente secuencial.

Uso:
    from eidos.utils.persistence import apply_migrations
    apply_migrations(db_path, migrations_dir)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from eidos.utils.logging import get_logger

logger = get_logger(__name__)


def apply_migrations(db_path: Path, migrations_dir: Path) -> int:
    """Aplica todas las migraciones pendientes.

    Returns:
        Número de migraciones nuevas aplicadas.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    migrations_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _ensure_bookkeeping_table(conn)

        applied = _applied_versions(conn)
        pending = _pending_migrations(migrations_dir, applied)

        for version, sql_path in pending:
            _apply_one(conn, version, sql_path)
            logger.info("migration_applied", version=version, file=sql_path.name)

        return len(pending)
    finally:
        conn.close()


def _ensure_bookkeeping_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT    NOT NULL
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    cur = conn.execute("SELECT version FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def _pending_migrations(migrations_dir: Path, applied: set[int]) -> list[tuple[int, Path]]:
    files = sorted(migrations_dir.glob("*.sql"))
    pending: list[tuple[int, Path]] = []
    for f in files:
        # 0001_initial.sql -> version 1
        try:
            version = int(f.stem.split("_", 1)[0])
        except ValueError:
            logger.warning("migration_skipped_invalid_name", file=str(f))
            continue
        if version not in applied:
            pending.append((version, f))
    return pending


def _apply_one(conn: sqlite3.Connection, version: int, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        conn.executescript(sql)
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, ts),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("migration_failed", version=version, error=str(e))
        raise RuntimeError(f"Migration {version} failed: {e}") from e


__all__ = ["apply_migrations"]
