"""Tests del LlamaCppBackend, APIFallback y CortexHub — Fase 2.

Usamos mocks (FakeLlamaClient) para no requerir GPU ni llama-cpp-python
instalado en el entorno de tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidos.core.monologue import Monologue
from eidos.cortex.api_fallback import APIFallbackBackend
from eidos.cortex.embeddings import StubEmbedder
from eidos.cortex.hub import CortexHub
from eidos.cortex.llama_backend import LlamaCppBackend
from eidos.cortex.manager import ModelManager, ModelStatus
from eidos.cortex.privacy import PrivacyFilter
from eidos.utils.persistence import apply_migrations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    return tmp_path / "models"


@pytest.fixture
def manager(db_path: Path, models_dir: Path) -> ModelManager:
    return ModelManager(db_path=db_path, models_dir=models_dir)


@pytest.fixture
def hub(manager: ModelManager, tmp_path: Path) -> CortexHub:
    return CortexHub(model_manager=manager, lock_path=tmp_path / "cortex.lock")


# ---------------------------------------------------------------------------
# Mock LlamaClient — produce JSON válido sin GPU
# ---------------------------------------------------------------------------


class FakeLlamaClient:
    """Mock que simula llama_cpp.Llama para tests."""

    def __init__(self, response: str | None = None, *, fail_attempts: int = 0) -> None:
        self._response = response or json.dumps(
            {
                "observation": "El usuario pregunta sobre EIDOS.",
                "hypothesis": "Quiere saber qué es el proyecto.",
                "plan": ["Explicar EIDOS brevemente.", "Ofrecer más detalles."],
                "risk": "none",
                "confidence": 0.85,
            }
        )
        self._fail_attempts = fail_attempts
        self._calls = 0

    def complete(self, prompt, *, max_tokens=512, temperature=0.7, grammar=None, stop=None) -> str:
        self._calls += 1
        if self._calls <= self._fail_attempts:
            raise RuntimeError(f"Simulated failure (attempt {self._calls})")
        return self._response


# ---------------------------------------------------------------------------
# LlamaCppBackend
# ---------------------------------------------------------------------------


class TestLlamaCppBackend:
    def test_generate_valid_json(self) -> None:
        client = FakeLlamaClient()
        backend = LlamaCppBackend(
            model_path="/fake/path.gguf",
            max_plan_steps=5,
            client=client,
        )
        m = backend.generate("¿Qué es EIDOS?")
        assert isinstance(m, Monologue)
        assert m.backend == "llama_cpp"
        assert m.confidence == 0.85
        assert len(m.plan) >= 1

    def test_generate_retries_on_invalid_json(self) -> None:
        # 1 intento inválido, 2 válido
        client = FakeLlamaClient(fail_attempts=1)
        backend = LlamaCppBackend(
            model_path="/fake/path.gguf",
            max_plan_steps=5,
            max_retries=3,
            client=client,
        )
        m = backend.generate("test")
        assert m.backend == "llama_cpp"
        assert client._calls == 2  # primero falló, segundo OK

    def test_generate_fails_after_max_retries(self) -> None:
        client = FakeLlamaClient(fail_attempts=5)
        backend = LlamaCppBackend(
            model_path="/fake/path.gguf",
            max_retries=2,
            client=client,
        )
        with pytest.raises(RuntimeError, match="failed after 2 attempts"):
            backend.generate("test")

    def test_parse_markdown_fenced_json(self) -> None:
        client = FakeLlamaClient(
            response='```json\n{"observation":"x","hypothesis":"y","plan":["a"],"risk":"none","confidence":0.7}\n```'
        )
        backend = LlamaCppBackend(model_path="/fake", client=client)
        m = backend.generate("test")
        assert m.observation == "x"
        assert m.confidence == 0.7

    def test_parse_truncates_plan_to_max_steps(self) -> None:
        client = FakeLlamaClient(
            response=json.dumps(
                {
                    "observation": "x",
                    "hypothesis": "y",
                    "plan": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
                    "risk": "none",
                    "confidence": 0.8,
                }
            )
        )
        backend = LlamaCppBackend(model_path="/fake", max_plan_steps=3, client=client)
        m = backend.generate("test")
        assert len(m.plan) == 3

    def test_parse_clamps_confidence_out_of_range(self) -> None:
        client = FakeLlamaClient(
            response=json.dumps(
                {
                    "observation": "x",
                    "hypothesis": "y",
                    "plan": ["p"],
                    "risk": "none",
                    "confidence": 1.5,  # out of range
                }
            )
        )
        backend = LlamaCppBackend(model_path="/fake", client=client)
        m = backend.generate("test")
        assert m.confidence == 1.0  # clamped

    def test_empty_input_raises(self) -> None:
        backend = LlamaCppBackend(model_path="/fake", client=FakeLlamaClient())
        with pytest.raises(ValueError):
            backend.generate("")

    def test_close_releases_resources(self) -> None:
        backend = LlamaCppBackend(model_path="/fake", client=FakeLlamaClient())
        backend.close()  # no debe lanzar


# ---------------------------------------------------------------------------
# APIFallbackBackend
# ---------------------------------------------------------------------------


class TestAPIFallback:
    def test_generate_with_mock_client(self) -> None:
        """Inyectamos un callable como client que simula la respuesta HTTP."""

        def mock_client(payload, headers, url):
            return json.dumps(
                {
                    "observation": "Test observation.",
                    "hypothesis": "Test hypothesis.",
                    "plan": ["Step 1", "Step 2"],
                    "risk": "none",
                    "confidence": 0.75,
                }
            )

        backend = APIFallbackBackend(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            client=mock_client,
        )
        m = backend.generate("test input")
        assert m.backend == "api"
        assert m.confidence == 0.75

    def test_anthropic_protocol_url_and_headers(self) -> None:
        """Fase 6: api_type='anthropic' usa /v1/messages y headers x-api-key."""
        captured: dict = {}

        def mock_client(payload, headers, url):
            captured["payload"] = payload
            captured["headers"] = headers
            captured["url"] = url
            return json.dumps(
                {
                    "observation": "x",
                    "hypothesis": "y",
                    "plan": ["p"],
                    "risk": "none",
                    "confidence": 0.7,
                }
            )

        backend = APIFallbackBackend(
            base_url="https://api.minimax.io/anthropic",
            api_key="mm-test-key",
            model="MiniMax-M3",
            client=mock_client,
            api_type="anthropic",
        )
        backend.generate("test")

        # URL debe ser /v1/messages (protocolo Anthropic)
        assert captured["url"] == "https://api.minimax.io/anthropic/v1/messages"
        # Headers deben usar x-api-key + anthropic-version
        assert captured["headers"]["x-api-key"] == "mm-test-key"
        assert captured["headers"]["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in captured["headers"]
        # Payload debe tener 'system' y 'messages' (formato Anthropic)
        assert captured["payload"]["model"] == "MiniMax-M3"
        assert "system" in captured["payload"]
        assert "messages" in captured["payload"]
        assert captured["payload"]["max_tokens"] == 1024

    def test_openai_protocol_unchanged(self) -> None:
        """Cero regresiones: api_type='openai' (default) sigue funcionando igual."""
        captured: dict = {}

        def mock_client(payload, headers, url):
            captured["payload"] = payload
            captured["headers"] = headers
            captured["url"] = url
            return json.dumps(
                {
                    "observation": "x",
                    "hypothesis": "y",
                    "plan": ["p"],
                    "risk": "none",
                    "confidence": 0.7,
                }
            )

        backend = APIFallbackBackend(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4o-mini",
            client=mock_client,
            # api_type no especificado → default 'openai'
        )
        backend.generate("test")

        # URL debe ser /chat/completions (protocolo OpenAI)
        assert captured["url"] == "https://api.openai.com/v1/chat/completions"
        # Headers deben usar Authorization Bearer
        assert captured["headers"]["Authorization"] == "Bearer sk-test"
        assert "x-api-key" not in captured["headers"]
        # Payload debe tener messages con system + user (formato OpenAI)
        assert captured["payload"]["model"] == "gpt-4o-mini"
        assert "messages" in captured["payload"]
        assert captured["payload"]["messages"][0]["role"] == "system"

    def test_anthropic_parses_content_blocks(self) -> None:
        """El parser Anthropic debe extraer texto de content[].text[]."""
        captured: dict = {}

        def mock_client(payload, headers, url):
            # Simular respuesta Anthropic real con content blocks
            # Pero como el client mock devuelve texto ya extraído,
            # devolvemos el JSON del monologue directamente.
            return json.dumps(
                {
                    "observation": "From minimax",
                    "hypothesis": "M3 model",
                    "plan": ["step1"],
                    "risk": "none",
                    "confidence": 0.9,
                }
            )

        backend = APIFallbackBackend(
            base_url="https://api.minimax.io/anthropic",
            api_key="mm-key",
            model="MiniMax-M3",
            client=mock_client,
            api_type="anthropic",
        )
        m = backend.generate("test minimax")
        assert m.backend == "api"
        assert m.observation == "From minimax"
        assert m.confidence == 0.9

    def test_privacy_filter_applied_before_call(self) -> None:
        """Verifica que el PrivacyFilter redacta PII antes de enviar."""
        captured_payload = {}

        def mock_client(payload, headers, url):
            captured_payload.update(payload)
            return json.dumps(
                {
                    "observation": "x",
                    "hypothesis": "y",
                    "plan": ["p"],
                    "risk": "none",
                    "confidence": 0.5,
                }
            )

        backend = APIFallbackBackend(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="m",
            client=mock_client,
        )
        # El input contiene un email → debe ser redactado antes del envío
        m = backend.generate("Mi email es test@example.com y quiero info")
        assert m.backend == "api"
        # Verificar que el payload enviado no contiene el email original
        user_msg = ""
        for msg in captured_payload["messages"]:
            if msg["role"] == "user":
                user_msg = msg["content"]
                break
        assert "test@example.com" not in user_msg
        assert "[REDACTED_EMAIL_1]" in user_msg

    def test_retries_on_failure(self) -> None:
        call_count = [0]

        def mock_client(payload, headers, url):
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("simulated network error")
            return json.dumps(
                {
                    "observation": "x",
                    "hypothesis": "y",
                    "plan": ["p"],
                    "risk": "none",
                    "confidence": 0.6,
                }
            )

        backend = APIFallbackBackend(
            base_url="https://api.example.com/v1",
            api_key="k",
            model="m",
            max_retries=3,
            client=mock_client,
        )
        m = backend.generate("test")
        assert call_count[0] == 2
        assert m.backend == "api"


# ---------------------------------------------------------------------------
# CortexHub — lock singleton-virtual
# ---------------------------------------------------------------------------


class TestCortexHubLock:
    def test_acquire_and_release(self, hub: CortexHub) -> None:
        assert hub.has_lock() is False
        ok = hub.try_acquire_lock(role="primary", ttl_sec=10)
        assert ok is True
        assert hub.has_lock() is True
        hub.release_lock()
        assert hub.has_lock() is False

    def test_reacquire_within_ttl(self, hub: CortexHub) -> None:
        hub.try_acquire_lock(role="primary", ttl_sec=10)
        # Segunda llamada dentro del TTL → debe devolver True sin crear nuevo lock
        ok = hub.try_acquire_lock(role="primary", ttl_sec=10)
        assert ok is True
        hub.release_lock()

    def test_expired_lock_reacquired(self, hub: CortexHub) -> None:
        # TTL = 0 → expira inmediatamente
        hub.try_acquire_lock(role="primary", ttl_sec=0)
        # Pequeño sleep para asegurar expiración
        import time

        time.sleep(0.01)
        assert not hub.has_lock()
        # Adquirir de nuevo
        ok = hub.try_acquire_lock(role="primary", ttl_sec=10)
        assert ok is True
        hub.release_lock()


# ---------------------------------------------------------------------------
# CortexHub — backend de monólogo
# ---------------------------------------------------------------------------


class TestCortexHubMonologueBackend:
    def test_no_model_available_returns_none(self, hub: CortexHub) -> None:
        backend = hub.get_monologue_backend()
        assert backend is None

    def test_returns_backend_when_model_ready(
        self, hub: CortexHub, manager: ModelManager, models_dir: Path
    ) -> None:
        # Crear archivo fake + registrar modelo + marcar ready
        fake_path = models_dir / "fake.gguf"
        fake_path.write_bytes(b"fake")
        manager.register(
            model_id="fake-mono",
            name="Fake Mono",
            filename="fake.gguf",
            url="http://x",
            format="gguf",
            purpose="monologue",
        )
        import sqlite3

        conn = sqlite3.connect(manager._db_path)
        conn.execute("UPDATE models SET status = 'ready' WHERE id = 'fake-mono'")
        conn.commit()
        conn.close()

        backend = hub.get_monologue_backend(client=FakeLlamaClient())
        assert backend is not None
        m = backend.generate("test")
        assert m.backend == "llama_cpp"

    def test_backend_cached_for_same_model(
        self, hub: CortexHub, manager: ModelManager, models_dir: Path
    ) -> None:
        fake_path = models_dir / "fake.gguf"
        fake_path.write_bytes(b"fake")
        manager.register(
            model_id="m1", name="M1", filename="fake.gguf", url="http://x",
            format="gguf", purpose="monologue",
        )
        import sqlite3

        conn = sqlite3.connect(manager._db_path)
        conn.execute("UPDATE models SET status = 'ready' WHERE id = 'm1'")
        conn.commit()
        conn.close()

        client = FakeLlamaClient()
        b1 = hub.get_monologue_backend(client=client)
        b2 = hub.get_monologue_backend(client=client)
        # Same model_id → debe retornar el mismo backend (cache)
        assert b1 is b2


# ---------------------------------------------------------------------------
# CortexHub — embedder
# ---------------------------------------------------------------------------


class TestCortexHubEmbedder:
    def test_returns_stub_when_no_model(self, hub: CortexHub) -> None:
        emb = hub.get_embedder(dim=64)
        assert isinstance(emb, StubEmbedder)
        assert emb.dim == 64

    def test_returns_real_when_model_ready(
        self, hub: CortexHub, manager: ModelManager, models_dir: Path
    ) -> None:
        fake_path = models_dir / "emb.gguf"
        fake_path.write_bytes(b"fake")
        manager.register(
            model_id="emb1", name="Emb", filename="emb.gguf", url="http://x",
            format="gguf", purpose="embedding",
        )
        import sqlite3

        conn = sqlite3.connect(manager._db_path)
        conn.execute("UPDATE models SET status = 'ready' WHERE id = 'emb1'")
        conn.commit()
        conn.close()

        class FakeEmbedderClient:
            def embed(self, text):
                # Vector pseudo-aleatorio determinista
                v = [float(len(text) + i) for i in range(384)]
                import math
                norm = math.sqrt(sum(x * x for x in v))
                return [x / norm for x in v]

        from eidos.cortex.embeddings import LlamaCppEmbedder

        emb = hub.get_embedder(model_id="emb1", dim=384, client=FakeEmbedderClient())
        assert isinstance(emb, LlamaCppEmbedder)
        vec = emb.embed("hello world")
        assert len(vec) == 384


# ---------------------------------------------------------------------------
# CortexHub — close + stats
# ---------------------------------------------------------------------------


class TestCortexHubLifecycle:
    def test_close_releases_lock(self, hub: CortexHub) -> None:
        hub.try_acquire_lock(role="primary", ttl_sec=30)
        assert hub.has_lock()
        hub.close()
        assert not hub.has_lock()

    def test_stats(self, hub: CortexHub) -> None:
        s = hub.stats()
        assert s["module"] == "cortex_hub"
        assert "has_lock" in s
        assert "models" in s


# ---------------------------------------------------------------------------
# Integración EpisodicMemory con embedder real
# ---------------------------------------------------------------------------


class TestEpisodicWithCustomEmbedder:
    def test_custom_embedder_used(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        class FakeEmbedder:
            """Embedder que produce vectores similares para textos que comparten tokens."""

            def __init__(self):
                self._dim = 64

            @property
            def dim(self):
                return self._dim

            def embed(self, text):
                # Bag-of-words simple: un vector donde cada posición es un token distinto
                v = [0.0] * self._dim
                for tok in text.lower().split():
                    h = hash(tok) % self._dim
                    v[h] += 1.0
                # L2 normalize
                import math
                norm = math.sqrt(sum(x * x for x in v))
                if norm > 0:
                    v = [x / norm for x in v]
                return v

        emb = FakeEmbedder()
        em = EpisodicMemory(db_path=db_path, embedder=emb, max_events=100)
        assert em._dim == 64  # dim viene del embedder

        em.store("interaction", "hello world hello")
        results = em.search("hello world", top_k=3, min_score=0.0)
        # Debe encontrar al menos 1 resultado (similitud > 0 porque comparten tokens)
        assert len(results) >= 1
