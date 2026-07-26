"""Arbitrator — Fase 4.

Gestiona resource_tokens. El Leader es quien arbitra; los Workers
piden tokens vía RPC `acquire_token`.

Recursos arbitrables:
- 'cortex' — acceso exclusivo al LLM local (evita OOM por doble carga).
- 'memory_write' — escritura a la DB consolidada (single-writer).
- 'sandbox' — uso del ToolSandbox (limita paralelismo).

Cada token tiene:
- token_id (UUID)
- resource (str)
- holder_node_id (str)
- acquired_at, expires_at (TTL anti-deadlock)
- released_at (None hasta liberación)

API:
    arb = ResourceArbitrator(db_path, leader_node_id)
    token = arb.acquire(resource='cortex', holder='worker-1', ttl_sec=30)
    if token:
        # usar recurso
        arb.release(token.token_id)
    arb.expire_due()  # llamada periódica para limpiar tokens expirados
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eidos.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ResourceToken:
    token_id: str
    resource: str
    holder_node_id: str
    acquired_at: str
    expires_at: str
    released_at: str | None = None
    metadata: dict[str, Any] | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.released_at is not None:
            return True
        now = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        return now >= expires

    def is_active(self, now: datetime | None = None) -> bool:
        return not self.is_expired(now)


class ResourceArbitrator:
    """Arbitra recursos exclusivos entre nodos del MESH."""

    def __init__(self, db_path: Path, leader_node_id: str) -> None:
        self._db_path = db_path
        self._leader_id = leader_node_id

    # ---------------- API pública ----------------

    def acquire(
        self,
        resource: str,
        holder_node_id: str,
        ttl_sec: float = 30.0,
        metadata: dict[str, Any] | None = None,
    ) -> ResourceToken | None:
        """Intenta adquirir un token para el recurso. Si ya está tomado
        y no expirado, devuelve None.

        Returns:
            ResourceToken si se adquirió; None si el recurso está ocupado.
        """
        if not resource or not holder_node_id:
            raise ValueError("resource and holder_node_id are required")

        # Verificar si ya hay un token activo para este recurso
        existing = self._get_active_token(resource)
        if existing is not None:
            # ¿Es del mismo holder? Renovar.
            if existing.holder_node_id == holder_node_id:
                return self._renew(existing, ttl_sec)
            logger.info(
                "mesh_token_acquire_denied",
                resource=resource,
                holder=existing.holder_node_id,
                requester=holder_node_id,
            )
            return None

        # Crear nuevo token
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(1.0, ttl_sec))
        token = ResourceToken(
            token_id=str(uuid.uuid4()),
            resource=resource,
            holder_node_id=holder_node_id,
            acquired_at=now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            expires_at=expires.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            released_at=None,
            metadata=metadata or {},
        )
        self._persist(token)
        logger.info(
            "mesh_token_acquired",
            token_id=token.token_id,
            resource=resource,
            holder=holder_node_id,
            ttl=ttl_sec,
        )
        return token

    def release(self, token_id: str) -> bool:
        """Libera un token. Devuelve True si existía y estaba activo."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "UPDATE resource_tokens SET released_at = ? WHERE token_id = ? AND released_at IS NULL",
                (now, token_id),
            )
            conn.commit()
            released = cur.rowcount > 0
            if released:
                logger.info("mesh_token_released", token_id=token_id)
            return released
        finally:
            conn.close()

    def release_all_for_holder(self, holder_node_id: str) -> int:
        """Libera todos los tokens activos de un holder (p.ej. al desconectarse)."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "UPDATE resource_tokens SET released_at = ? "
                "WHERE holder_node_id = ? AND released_at IS NULL",
                (now, holder_node_id),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def get_active_token(self, resource: str) -> ResourceToken | None:
        """Devuelve el token activo para un recurso, o None."""
        return self._get_active_token(resource)

    def list_active(self) -> list[ResourceToken]:
        conn = self._conn()
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "SELECT token_id, resource, holder_node_id, acquired_at, expires_at, released_at, metadata "
                "FROM resource_tokens WHERE released_at IS NULL AND expires_at > ?",
                (now_iso,),
            )
            return [self._row_to_token(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def expire_due(self) -> int:
        """Marca como released todos los tokens que han expirado (TTL vencido).
        Devuelve el número de tokens expirados."""
        conn = self._conn()
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "UPDATE resource_tokens SET released_at = ? "
                "WHERE released_at IS NULL AND expires_at <= ?",
                (now_iso, now_iso),
            )
            conn.commit()
            expired = cur.rowcount
            if expired > 0:
                logger.info("mesh_tokens_expired", count=expired)
            return expired
        finally:
            conn.close()

    def stats(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "SELECT COUNT(*) FROM resource_tokens WHERE released_at IS NULL AND expires_at > ?",
                (now_iso,),
            )
            active = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT resource, COUNT(*) FROM resource_tokens "
                "WHERE released_at IS NULL AND expires_at > ? GROUP BY resource",
                (now_iso,),
            )
            by_resource = {row[0]: row[1] for row in cur.fetchall()}
            cur = conn.execute("SELECT COUNT(*) FROM resource_tokens")
            total = cur.fetchone()[0]
        finally:
            conn.close()
        return {
            "module": "arbitrator",
            "leader_id": self._leader_id,
            "active_tokens": active,
            "total_ever": total,
            "by_resource": by_resource,
        }

    # ---------------- internal ----------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _get_active_token(self, resource: str) -> ResourceToken | None:
        conn = self._conn()
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cur = conn.execute(
                "SELECT token_id, resource, holder_node_id, acquired_at, expires_at, released_at, metadata "
                "FROM resource_tokens WHERE resource = ? AND released_at IS NULL AND expires_at > ? "
                "ORDER BY acquired_at DESC LIMIT 1",
                (resource, now_iso),
            )
            r = cur.fetchone()
            return self._row_to_token(r) if r else None
        finally:
            conn.close()

    def _renew(self, existing: ResourceToken, ttl_sec: float) -> ResourceToken:
        """Extiende el TTL de un token existente del mismo holder."""
        new_expires = datetime.now(timezone.utc) + timedelta(seconds=max(1.0, ttl_sec))
        new_expires_iso = new_expires.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE resource_tokens SET expires_at = ? WHERE token_id = ?",
                (new_expires_iso, existing.token_id),
            )
            conn.commit()
        finally:
            conn.close()
        renewed = ResourceToken(
            token_id=existing.token_id,
            resource=existing.resource,
            holder_node_id=existing.holder_node_id,
            acquired_at=existing.acquired_at,
            expires_at=new_expires_iso,
            released_at=None,
            metadata=existing.metadata,
        )
        logger.info(
            "mesh_token_renewed",
            token_id=existing.token_id,
            resource=existing.resource,
            new_ttl=ttl_sec,
        )
        return renewed

    def _persist(self, token: ResourceToken) -> None:
        import json

        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO resource_tokens
                (token_id, resource, holder_node_id, acquired_at, expires_at, released_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token.token_id,
                    token.resource,
                    token.holder_node_id,
                    token.acquired_at,
                    token.expires_at,
                    token.released_at,
                    json.dumps(token.metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_token(r: tuple[Any, ...]) -> ResourceToken:
        import json

        return ResourceToken(
            token_id=r[0],
            resource=r[1],
            holder_node_id=r[2],
            acquired_at=r[3],
            expires_at=r[4],
            released_at=r[5],
            metadata=json.loads(r[6] or "{}"),
        )


__all__ = ["ResourceArbitrator", "ResourceToken"]
