"""Tests del sistema de migraciones SQL versionadas."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from eidos.utils.persistence import apply_migrations


def test_apply_migrations_creates_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "0001_initial.sql").write_text(
        "CREATE TABLE foo (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'now');\n",
        encoding="utf-8",
    )

    n = apply_migrations(db, mig_dir)
    assert n == 1

    conn = sqlite3.connect(db)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        assert "foo" in tables
        assert "schema_migrations" in tables
    finally:
        conn.close()


def test_apply_migrations_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "0001_initial.sql").write_text(
        "CREATE TABLE foo (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'now');\n",
        encoding="utf-8",
    )

    apply_migrations(db, mig_dir)
    n = apply_migrations(db, mig_dir)
    assert n == 0


def test_apply_migrations_multiple_versions(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "0001_a.sql").write_text(
        "CREATE TABLE a (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'now');\n",
        encoding="utf-8",
    )
    (mig_dir / "0002_b.sql").write_text(
        "CREATE TABLE b (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO schema_migrations(version, applied_at) VALUES (2, 'now');\n",
        encoding="utf-8",
    )

    n = apply_migrations(db, mig_dir)
    assert n == 2

    conn = sqlite3.connect(db)
    try:
        cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        versions = [row[0] for row in cur.fetchall()]
        assert versions == [1, 2]
    finally:
        conn.close()


def test_apply_migrations_invalid_name_skipped(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "broken.sql").write_text(
        "CREATE TABLE x (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )

    # No debe romper, solo saltar
    n = apply_migrations(db, mig_dir)
    assert n == 0
