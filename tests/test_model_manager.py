"""Tests del ModelManager — Fase 2.1."""

from __future__ import annotations

import hashlib
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

import pytest

from eidos.cortex.manager import ModelInfo, ModelManager, ModelStatus
from eidos.utils.persistence import apply_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    d = tmp_path / "models"
    d.mkdir()
    return d


@pytest.fixture
def manager(db_path: Path, models_dir: Path) -> ModelManager:
    return ModelManager(db_path=db_path, models_dir=models_dir)


# ---------------------------------------------------------------------------
# Registro y consulta
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_get(self, manager: ModelManager) -> None:
        info = manager.register(
            model_id="qwen-test",
            name="Qwen2.5-3B Test",
            filename="qwen-test.gguf",
            url="https://example.com/qwen.gguf",
            format="gguf",
            purpose="monologue",
            quantization="Q4_K_M",
        )
        assert info.id == "qwen-test"
        assert info.status == ModelStatus.ABSENT.value

        fetched = manager.get("qwen-test")
        assert fetched is not None
        assert fetched.name == "Qwen2.5-3B Test"

    def test_list_all(self, manager: ModelManager) -> None:
        manager.register(
            model_id="m1", name="M1", filename="m1.gguf", url="u1",
            format="gguf", purpose="monologue",
        )
        manager.register(
            model_id="m2", name="M2", filename="m2.gguf", url="u2",
            format="gguf", purpose="embedding",
        )
        all_models = manager.list_all()
        assert len(all_models) == 2

    def test_list_by_purpose(self, manager: ModelManager) -> None:
        manager.register(
            model_id="m1", name="M1", filename="m1.gguf", url="u1",
            format="gguf", purpose="monologue",
        )
        manager.register(
            model_id="m2", name="M2", filename="m2.gguf", url="u2",
            format="gguf", purpose="embedding",
        )
        mono = manager.list_by_purpose("monologue")
        assert len(mono) == 1
        assert mono[0].id == "m1"

    def test_register_upsert_updates_fields(self, manager: ModelManager) -> None:
        manager.register(
            model_id="m1", name="Original", filename="m1.gguf", url="u1",
            format="gguf", purpose="monologue",
        )
        manager.register(
            model_id="m1", name="Updated", filename="m1.gguf", url="u2",
            format="gguf", purpose="monologue", quantization="Q5_K_M",
        )
        info = manager.get("m1")
        assert info is not None
        assert info.name == "Updated"
        assert info.url == "u2"
        assert info.quantization == "Q5_K_M"


# ---------------------------------------------------------------------------
# Descarga con servidor HTTP local
# ---------------------------------------------------------------------------


class TestDownload:
    @pytest.fixture
    def http_server(self, tmp_path: Path):
        """Servidor HTTP local que sirve un archivo pequeño para tests."""
        payload = b"EIDOS test model payload" * 100  # ~2.4 KB

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/model.gguf":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_HEAD(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()

            def log_message(self, *args):  # silence
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        # Guardar el payload para verificación SHA256
        sha = hashlib.sha256(payload).hexdigest()
        yield port, sha, payload
        server.shutdown()
        thread.join(timeout=2)

    def test_download_success(
        self, manager: ModelManager, models_dir: Path, http_server
    ) -> None:
        port, sha, payload = http_server
        url = f"http://127.0.0.1:{port}/model.gguf"

        manager.register(
            model_id="test-model",
            name="Test Model",
            filename="test.gguf",
            url=url,
            format="gguf",
            purpose="monologue",
            sha256=sha,
        )

        path = manager.download("test-model")
        assert path.exists()
        assert path.read_bytes() == payload

        info = manager.get("test-model")
        assert info is not None
        assert info.status == ModelStatus.READY.value
        assert info.downloaded_at is not None
        assert info.size_bytes == len(payload)

    def test_download_sha256_mismatch(
        self, manager: ModelManager, models_dir: Path, http_server
    ) -> None:
        port, sha, _ = http_server
        url = f"http://127.0.0.1:{port}/model.gguf"

        manager.register(
            model_id="bad-model",
            name="Bad",
            filename="bad.gguf",
            url=url,
            format="gguf",
            purpose="monologue",
            sha256="0" * 64,  # sha incorrecto a propósito
        )

        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            manager.download("bad-model")

        info = manager.get("bad-model")
        assert info is not None
        assert info.status == ModelStatus.CORRUPT.value
        # El archivo corrupto debe borrarse
        assert not (models_dir / "bad.gguf").exists()

    def test_download_unregistered_raises(self, manager: ModelManager) -> None:
        with pytest.raises(ValueError, match="not registered"):
            manager.download("nonexistent")

    def test_download_already_ready_skips(
        self, manager: ModelManager, models_dir: Path, http_server
    ) -> None:
        port, sha, _ = http_server
        url = f"http://127.0.0.1:{port}/model.gguf"
        manager.register(
            model_id="ready",
            name="R",
            filename="r.gguf",
            url=url,
            format="gguf",
            purpose="monologue",
            sha256=sha,
        )
        # Primera descarga
        path1 = manager.download("ready")
        mtime1 = path1.stat().st_mtime
        # Segunda descarga (debe skipear)
        path2 = manager.download("ready")
        assert path2 == path1
        assert path2.stat().st_mtime == mtime1  # no se re-descargó


# ---------------------------------------------------------------------------
# Eliminación y verificación
# ---------------------------------------------------------------------------


class TestDeleteAndVerify:
    def test_delete_removes_file(self, manager: ModelManager, models_dir: Path) -> None:
        # Crear archivo fake
        fake_path = models_dir / "fake.gguf"
        fake_path.write_bytes(b"fake content")
        manager.register(
            model_id="fake",
            name="Fake",
            filename="fake.gguf",
            url="http://example.com",
            format="gguf",
            purpose="monologue",
        )
        # Marcar como ready manualmente
        import sqlite3

        conn = sqlite3.connect(manager._db_path)
        conn.execute("UPDATE models SET status = 'ready' WHERE id = 'fake'")
        conn.commit()
        conn.close()

        ok = manager.delete("fake")
        assert ok is True
        assert not fake_path.exists()
        info = manager.get("fake")
        assert info is not None
        assert info.status == ModelStatus.ABSENT.value

    def test_delete_nonexistent_returns_false(self, manager: ModelManager) -> None:
        assert manager.delete("nonexistent") is False

    def test_verify_without_checksum_returns_true(self, manager: ModelManager, models_dir: Path) -> None:
        fake_path = models_dir / "v.gguf"
        fake_path.write_bytes(b"x")
        manager.register(
            model_id="v",
            name="V",
            filename="v.gguf",
            url="http://x",
            format="gguf",
            purpose="monologue",
        )
        # Marcar como ready
        import sqlite3

        conn = sqlite3.connect(manager._db_path)
        conn.execute("UPDATE models SET status = 'ready' WHERE id = 'v'")
        conn.commit()
        conn.close()
        # Sin sha256 registrado → verifica solo que el archivo existe
        assert manager.verify("v") is True

    def test_resolve_path(self, manager: ModelManager, models_dir: Path) -> None:
        fake_path = models_dir / "r.gguf"
        fake_path.write_bytes(b"x")
        manager.register(
            model_id="r",
            name="R",
            filename="r.gguf",
            url="http://x",
            format="gguf",
            purpose="monologue",
        )
        # Sin status=ready → None
        assert manager.resolve_path("r") is None
        # Con status=ready
        import sqlite3

        conn = sqlite3.connect(manager._db_path)
        conn.execute("UPDATE models SET status = 'ready' WHERE id = 'r'")
        conn.commit()
        conn.close()
        path = manager.resolve_path("r")
        assert path is not None
        assert path.name == "r.gguf"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_returns_metrics(self, manager: ModelManager) -> None:
        manager.register(
            model_id="m1", name="M1", filename="m1.gguf", url="u1",
            format="gguf", purpose="monologue",
        )
        s = manager.stats()
        assert s["module"] == "model_manager"
        assert "absent" in s["by_status"]
        assert s["by_status"]["absent"]["count"] == 1
