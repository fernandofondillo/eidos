"""ModelManager — Fase 2.1.

Gestiona la descarga, verificación y registro de modelos GGUF/ONNX
locales en /models. Sin Ollama, sin LM Studio — descarga HTTP directa
desde HuggingFace u otros mirrors.

Características:
- Descarga con soporte resume (HTTP Range).
- Verificación SHA256.
- Registro en SQLite (tabla `models`).
- Listar / status / eliminar modelos.
- Configuración declarativa en config/eidos.yaml bajo `cortex.models_manifest`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from eidos.utils.logging import get_logger

logger = get_logger(__name__)


class ModelStatus(str, Enum):
    ABSENT = "absent"
    DOWNLOADING = "downloading"
    READY = "ready"
    CORRUPT = "corrupt"


@dataclass
class ModelInfo:
    id: str
    name: str
    filename: str
    url: str
    sha256: str | None
    size_bytes: int | None
    format: str
    quantization: str | None
    purpose: str
    status: str
    downloaded_at: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "filename": self.filename,
            "url": self.url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "format": self.format,
            "quantization": self.quantization,
            "purpose": self.purpose,
            "status": self.status,
            "downloaded_at": self.downloaded_at,
            "metadata": self.metadata,
        }


class ModelManager:
    """Gestor de modelos locales GGUF/ONNX."""

    # Tamaño de chunk para descarga (256 KB)
    _CHUNK_SIZE = 256 * 1024

    def __init__(self, db_path: Path, models_dir: Path) -> None:
        self._db_path = db_path
        self._models_dir = models_dir
        self._models_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- Registro y consulta ----------------

    def register(
        self,
        model_id: str,
        name: str,
        filename: str,
        url: str,
        format: str,
        purpose: str,
        quantization: str | None = None,
        sha256: str | None = None,
        size_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelInfo:
        """Registra (o actualiza) un modelo en el catálogo."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO models(id, name, filename, url, sha256, size_bytes,
                                   format, quantization, purpose, status, downloaded_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    filename=excluded.filename,
                    url=excluded.url,
                    sha256=excluded.sha256,
                    size_bytes=excluded.size_bytes,
                    format=excluded.format,
                    quantization=excluded.quantization,
                    purpose=excluded.purpose,
                    metadata=excluded.metadata
                """,
                (
                    model_id, name, filename, url, sha256, size_bytes,
                    format, quantization, purpose, ModelStatus.ABSENT.value,
                    None, json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        info = self.get(model_id)
        assert info is not None
        return info

    def get(self, model_id: str) -> ModelInfo | None:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, name, filename, url, sha256, size_bytes, format, "
                "quantization, purpose, status, downloaded_at, metadata "
                "FROM models WHERE id = ?",
                (model_id,),
            )
            r = cur.fetchone()
            return self._row_to_info(r) if r else None
        finally:
            conn.close()

    def list_all(self) -> list[ModelInfo]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, name, filename, url, sha256, size_bytes, format, "
                "quantization, purpose, status, downloaded_at, metadata "
                "FROM models ORDER BY name"
            )
            return [self._row_to_info(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_by_purpose(self, purpose: str) -> list[ModelInfo]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, name, filename, url, sha256, size_bytes, format, "
                "quantization, purpose, status, downloaded_at, metadata "
                "FROM models WHERE purpose = ? ORDER BY name",
                (purpose,),
            )
            return [self._row_to_info(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # ---------------- Descarga ----------------

    def download(
        self,
        model_id: str,
        expected_sha256: str | None = None,
        force: bool = False,
        progress_callback: Any = None,
    ) -> Path:
        """Descarga un modelo registrado. Verifica SHA256 si se provee.

        Args:
            model_id: ID del modelo registrado.
            expected_sha256: Si es None, usa el sha256 del registro.
            force: Si True, redescarga incluso si status='ready'.
            progress_callback: callable(received_bytes, total_bytes) opcional.

        Returns:
            Path al archivo descargado.
        """
        info = self.get(model_id)
        if info is None:
            raise ValueError(f"Model '{model_id}' not registered. Call register() first.")

        target_path = self._models_dir / info.filename

        # Si ya está listo y no forzamos, devolver
        if info.status == ModelStatus.READY.value and not force and target_path.exists():
            logger.info("model_already_ready", model_id=model_id, path=str(target_path))
            return target_path

        sha = expected_sha256 or info.sha256

        # Marcar como downloading
        self._set_status(model_id, ModelStatus.DOWNLOADING)

        try:
            self._download_with_resume(
                url=info.url,
                target_path=target_path,
                progress_callback=progress_callback,
            )
        except (HTTPError, URLError) as e:
            self._set_status(model_id, ModelStatus.ABSENT)
            logger.error("model_download_failed", model_id=model_id, error=str(e))
            raise RuntimeError(f"Download failed for {model_id}: {e}") from e

        # Verificar SHA256 si se especificó
        if sha:
            actual_sha = self._sha256_of(target_path)
            if actual_sha != sha:
                self._set_status(model_id, ModelStatus.CORRUPT)
                target_path.unlink(missing_ok=True)
                logger.error(
                    "model_sha256_mismatch",
                    model_id=model_id,
                    expected=sha[:16],
                    actual=actual_sha[:16],
                )
                raise RuntimeError(
                    f"SHA256 mismatch for {model_id}: expected {sha}, got {actual_sha}"
                )

        # Actualizar registro
        size = target_path.stat().st_size
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE models SET status = ?, downloaded_at = ?, size_bytes = ? WHERE id = ?",
                (ModelStatus.READY.value, now, size, model_id),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("model_downloaded", model_id=model_id, size_bytes=size, path=str(target_path))
        return target_path

    def delete(self, model_id: str) -> bool:
        """Elimina el archivo y marca el modelo como absent."""
        info = self.get(model_id)
        if info is None:
            return False
        target = self._models_dir / info.filename
        deleted_file = False
        if target.exists():
            target.unlink()
            deleted_file = True
        self._set_status(model_id, ModelStatus.ABSENT)
        # Limpiar downloaded_at
        conn = self._conn()
        try:
            conn.execute("UPDATE models SET downloaded_at = NULL WHERE id = ?", (model_id,))
            conn.commit()
        finally:
            conn.close()
        logger.info("model_deleted", model_id=model_id, file_deleted=deleted_file)
        return True

    def verify(self, model_id: str) -> bool:
        """Verifica que un modelo en disco coincide con el SHA256 registrado."""
        info = self.get(model_id)
        if info is None:
            return False
        target = self._models_dir / info.filename
        if not target.exists():
            return False
        if not info.sha256:
            return True  # sin checksum registrado, asumimos OK
        actual = self._sha256_of(target)
        ok = actual == info.sha256
        new_status = ModelStatus.READY if ok else ModelStatus.CORRUPT
        self._set_status(model_id, new_status)
        return ok

    def resolve_path(self, model_id: str) -> Path | None:
        """Devuelve la ruta absoluta al archivo del modelo, o None si no está listo."""
        info = self.get(model_id)
        if info is None or info.status != ModelStatus.READY.value:
            return None
        p = self._models_dir / info.filename
        return p if p.exists() else None

    # ---------------- interno: descarga con resume ----------------

    def _download_with_resume(
        self,
        url: str,
        target_path: Path,
        progress_callback: Any = None,
    ) -> None:
        """Descarga HTTP con soporte resume (Range). Crea .part temporal."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = target_path.with_suffix(target_path.suffix + ".part")

        # Tamaño ya descargado (para resume)
        existing_size = part_path.stat().st_size if part_path.exists() else 0

        req = urllib.request.Request(url)
        if existing_size > 0:
            req.add_header("Range", f"bytes={existing_size}-")

        with urllib.request.urlopen(req, timeout=60) as response:
            total_header = response.getheader("Content-Length")
            # Si el servidor responde 200 (no 206), no podemos resumir; empezar de cero
            if existing_size > 0 and response.status == 200:
                existing_size = 0
                mode = "wb"
            else:
                mode = "ab"

            total = int(total_header) + existing_size if total_header else None

            with open(part_path, mode) as f:
                received = existing_size
                while True:
                    chunk = response.read(self._CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if progress_callback:
                        progress_callback(received, total)

        # Renombrar .part → final (atómico)
        part_path.replace(target_path)

    # ---------------- interno: utils ----------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _set_status(self, model_id: str, status: ModelStatus) -> None:
        conn = self._conn()
        try:
            conn.execute("UPDATE models SET status = ? WHERE id = ?", (status.value, model_id))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _sha256_of(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _row_to_info(r: tuple[Any, ...]) -> ModelInfo:
        return ModelInfo(
            id=r[0],
            name=r[1],
            filename=r[2],
            url=r[3],
            sha256=r[4],
            size_bytes=r[5],
            format=r[6],
            quantization=r[7],
            purpose=r[8],
            status=r[9],
            downloaded_at=r[10],
            metadata=json.loads(r[11] or "{}"),
        )

    def stats(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT status, COUNT(*), COALESCE(SUM(size_bytes),0) FROM models GROUP BY status"
            )
            by_status = {row[0]: {"count": row[1], "size_bytes": row[2]} for row in cur.fetchall()}
        finally:
            conn.close()
        total_disk = sum(
            f.stat().st_size for f in self._models_dir.glob("*") if f.is_file()
        )
        return {
            "module": "model_manager",
            "models_dir": str(self._models_dir),
            "by_status": by_status,
            "disk_usage_bytes": total_disk,
        }


__all__ = ["ModelManager", "ModelInfo", "ModelStatus"]
