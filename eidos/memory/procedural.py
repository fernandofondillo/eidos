"""Capa 4 — Memoria Procedimental (Cerebelo).

Almacena las "Herramientas/Skills" y Cápsulas que EIDOS ha creado
o aprendido. En Fase 1.2 solo la **infraestructura de persistencia**
(crear, listar, marcar favorita, expirar por TTL). La **génesis**
automática de cápsulas llega en Fase 3.

Cada cápsula se persiste en:
- Disco:  data/capsules/<id>.eidos (JSON)
- Índice: tabla `capsules` en SQLite (con TTL, uses, last_used, favorite)

El consolidador (Fase 1.3) revisa TTL y elimina las no-favoritas
caducadas.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eidos.memory.base import MemoryLayer
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class CapsuleRecord:
    """DTO simple para una cápsula (no es Pydantic todavía — Fase 3 lo promueve)."""

    def __init__(
        self,
        id: str,
        name: str,
        version: str,
        description: str,
        file_path: str,
        created_at: str,
        ttl_days: int = 7,
        uses: int = 0,
        last_used: str | None = None,
        favorite: bool = False,
        genesis_confidence: float | None = None,
        parent_capsule_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.version = version
        self.description = description
        self.file_path = file_path
        self.created_at = created_at
        self.ttl_days = ttl_days
        self.uses = uses
        self.last_used = last_used
        self.favorite = favorite
        self.genesis_confidence = genesis_confidence
        self.parent_capsule_id = parent_capsule_id
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "file_path": self.file_path,
            "created_at": self.created_at,
            "ttl_days": self.ttl_days,
            "uses": self.uses,
            "last_used": self.last_used,
            "favorite": self.favorite,
            "genesis_confidence": self.genesis_confidence,
            "parent_capsule_id": self.parent_capsule_id,
            "metadata": self.metadata,
        }


class ProceduralMemory(MemoryLayer):
    """Capa 4: registro de cápsulas."""

    layer_name = "procedural"

    def __init__(self, db_path: Path, capsules_dir: Path, default_ttl_days: int = 7) -> None:
        self._db_path = db_path
        self._capsules_dir = capsules_dir
        self._default_ttl_days = default_ttl_days
        self._capsules_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- public API ----------------

    def store(
        self,
        name: str,
        version: str,
        description: str,
        content: dict[str, Any],
        ttl_days: int | None = None,
        favorite: bool = False,
        genesis_confidence: float | None = None,
        parent_capsule_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CapsuleRecord:
        """Crea una nueva cápsula en disco + la indexa en SQLite.

        `content` es el cuerpo del .eidos (se persiste como JSON).
        """
        if not name or not version:
            raise ValueError("name and version are required")
        capsule_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        created_at = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ttl = ttl_days if ttl_days is not None else self._default_ttl_days

        # 1. Persistir archivo .eidos
        file_name = f"{capsule_id}.eidos"
        file_path = self._capsules_dir / file_name
        capsule_doc = {
            "id": capsule_id,
            "name": name,
            "version": version,
            "description": description,
            "content": content,
            "metadata": {
                "created_at": created_at,
                "ttl_days": ttl,
                "uses": 0,
                "last_used": None,
                "favorite": favorite,
                "genesis_confidence": genesis_confidence,
                "parent_capsule_id": parent_capsule_id,
                **(metadata or {}),
            },
        }
        file_path.write_text(
            json.dumps(capsule_doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 2. Indexar en SQLite
        rel_path = str(file_path.relative_to(self._capsules_dir.parent.parent))  # relativo a project root
        record = CapsuleRecord(
            id=capsule_id,
            name=name,
            version=version,
            description=description,
            file_path=rel_path,
            created_at=created_at,
            ttl_days=ttl,
            uses=0,
            last_used=None,
            favorite=favorite,
            genesis_confidence=genesis_confidence,
            parent_capsule_id=parent_capsule_id,
            metadata=metadata or {},
        )
        self._upsert(record)
        logger.info("capsule_stored", id=capsule_id, name=name, version=version)
        return record

    def get(self, capsule_id: str) -> CapsuleRecord | None:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, name, version, description, file_path, created_at, "
                "ttl_days, uses, last_used, favorite, genesis_confidence, "
                "parent_capsule_id, metadata FROM capsules WHERE id = ?",
                (capsule_id,),
            )
            r = cur.fetchone()
            return self._row_to_record(r) if r else None
        finally:
            conn.close()

    def list_all(self, include_expired: bool = False) -> list[CapsuleRecord]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, name, version, description, file_path, created_at, "
                "ttl_days, uses, last_used, favorite, genesis_confidence, "
                "parent_capsule_id, metadata FROM capsules ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        records = [self._row_to_record(r) for r in rows]
        if include_expired:
            return records
        return [r for r in records if r is not None and not self._is_expired(r)]

    def mark_used(self, capsule_id: str) -> None:
        """Incrementa `uses` y actualiza `last_used`. No-op si no existe."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE capsules SET uses = uses + 1, last_used = ? WHERE id = ?",
                (now, capsule_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_favorite(self, capsule_id: str, favorite: bool) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE capsules SET favorite = ? WHERE id = ?",
                (1 if favorite else 0, capsule_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, capsule_id: str) -> bool:
        """Elimina índice + archivo. Devuelve True si existía."""
        record = self.get(capsule_id)
        if record is None:
            return False
        # Borrar archivo
        try:
            full_path = self._capsules_dir.parent.parent / record.file_path
            if full_path.exists():
                full_path.unlink()
        except OSError as e:
            logger.warning("capsule_file_delete_failed", id=capsule_id, error=str(e))
        # Borrar índice
        conn = self._conn()
        try:
            conn.execute("DELETE FROM capsules WHERE id = ?", (capsule_id,))
            conn.commit()
        finally:
            conn.close()
        logger.info("capsule_deleted", id=capsule_id)
        return True

    def expire_due(self) -> list[str]:
        """Devuelve IDs de cápsulas no-favoritas caducadas por TTL."""
        records = self.list_all(include_expired=True)
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        for r in records:
            if r.favorite:
                continue
            if self._is_expired(r, now=now):
                expired.append(r.id)
        return expired

    def clear(self) -> int:
        """Borra todas las cápsulas NO favoritas. Devuelve número eliminadas."""
        records = self.list_all(include_expired=True)
        count = 0
        for r in records:
            if not r.favorite:
                if self.delete(r.id):
                    count += 1
        return count

    def stats(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT COUNT(*), SUM(favorite), SUM(uses) FROM capsules"
            )
            total, favs, total_uses = cur.fetchone()
        finally:
            conn.close()
        return {
            "layer": self.layer_name,
            "total": total or 0,
            "favorites": favs or 0,
            "total_uses": total_uses or 0,
            "expired_pending": len(self.expire_due()),
            "default_ttl_days": self._default_ttl_days,
        }

    # ---------------- internal ----------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _upsert(self, record: CapsuleRecord) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO capsules(id, name, version, description, file_path, created_at,
                                     ttl_days, uses, last_used, favorite, genesis_confidence,
                                     parent_capsule_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    description=excluded.description,
                    file_path=excluded.file_path,
                    ttl_days=excluded.ttl_days,
                    favorite=excluded.favorite,
                    metadata=excluded.metadata
                """,
                (
                    record.id, record.name, record.version, record.description,
                    record.file_path, record.created_at, record.ttl_days,
                    record.uses, record.last_used, 1 if record.favorite else 0,
                    record.genesis_confidence, record.parent_capsule_id,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_record(r: tuple[Any, ...]) -> CapsuleRecord | None:
        if r is None:
            return None
        return CapsuleRecord(
            id=r[0],
            name=r[1],
            version=r[2],
            description=r[3],
            file_path=r[4],
            created_at=r[5],
            ttl_days=r[6],
            uses=r[7],
            last_used=r[8],
            favorite=bool(r[9]),
            genesis_confidence=r[10],
            parent_capsule_id=r[11],
            metadata=json.loads(r[12] or "{}"),
        )

    def _is_expired(self, record: CapsuleRecord, now: datetime | None = None) -> bool:
        if record.favorite:
            return False
        now = now or datetime.now(timezone.utc)
        try:
            created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        last_used_str = record.last_used
        ref = created
        if last_used_str:
            try:
                ref = datetime.fromisoformat(last_used_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        return (now - ref).days >= record.ttl_days


__all__ = ["ProceduralMemory", "CapsuleRecord"]
