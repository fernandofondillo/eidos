"""Tests del Context Engine — verifica que EIDOS pasa historial al LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from eidos.core.engine import EidosCore
from eidos.core.monologue import MonologueGenerator
from eidos.memory.store import MemoryStore
from eidos.utils.persistence import apply_migrations


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    tmp_migrations = tmp_path / "data" / "migrations"
    tmp_migrations.mkdir(parents=True)
    for f in proj_migrations.glob("*.sql"):
        (tmp_migrations / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    config = {
        "memory": {
            "sensory": {"window_size": 50},
            "episodic": {"db_path": "data/eidos.db", "embedding_dim": 64, "max_events": 100},
            "semantic": {"graph_path": "data/graph.json"},
            "procedural": {"capsules_dir": "data/capsules", "default_ttl_days": 7},
        }
    }
    return MemoryStore.from_config(config, tmp_path)


class TestContextEngine:
    """Verifica que EIDOS construye y pasa contexto al LLM."""

    def test_first_message_has_no_history(self, memory_store: MemoryStore) -> None:
        """El primer mensaje no tiene historial previo."""
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        # Procesar primer mensaje
        resp = core.think_and_respond("hola")
        assert resp.text  # responde algo

        # Verificar que hay 1 evento sensorial (el input)
        assert memory_store.sensory.stats()["buffered"] >= 1

    def test_second_message_has_history(self, memory_store: MemoryStore) -> None:
        """Tras 2 mensajes, el historial debe estar disponible."""
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        # Primer intercambio
        core.think_and_respond("me llamo Fernando")
        # Segundo intercambio
        resp = core.think_and_respond("¿como me llamo?")
        assert resp.text

        # Verificar que hay eventos sensoriales (input + response)
        buffered = memory_store.sensory.stats()["buffered"]
        assert buffered >= 3  # 2 inputs + 1 response mínimo

    def test_semantic_extraction_from_explicit_pattern(self, memory_store: MemoryStore) -> None:
        """'Me llamo X' debe poblar el grafo semántico."""
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        core.think_and_respond("me llamo Fernando")
        # El grafo semántico debe tener al menos 1 nodo (usuario) + 1 arista
        stats = memory_store.semantic.stats()
        assert stats["nodes"] >= 1
        assert stats["edges"] >= 1

    def test_semantic_does_not_extract_from_llm_response(self, memory_store: MemoryStore) -> None:
        """La respuesta del LLM 'soy bastante curioso' NO debe guardarse como nombre."""
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        # El stub responde con texto que incluye "soy EIDOS" etc.
        core.think_and_respond("hola")
        # NO debe haber ningún nombre "eidos" o "curioso" en el grafo
        sem = memory_store.semantic
        rels = sem.query_relations("usuario", direction="out")
        for r in rels:
            if r.get("predicate") == "tiene_nombre":
                name = r.get("dst", "")
                assert "eidos" not in name
                assert "curioso" not in name
                assert "quien" not in name

    def test_capsule_relevant_to_input_is_detected(self, memory_store: MemoryStore) -> None:
        """Si hay una cápsula de Marketing y el usuario habla de marketing,
        la cápsula debe marcarse como usada."""
        from eidos.core.forge import CapsuleForge, StubForgeBackend

        forge = CapsuleForge(
            db_path=memory_store.db_path,
            procedural=memory_store.procedural,
            backend=StubForgeBackend(),
        )
        # Crear cápsula
        draft, decision = forge.forge("experto en marketing")
        assert decision.value == "auto_approved"

        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
        )
        # Hablar de marketing
        core.think_and_respond("hablame de estrategia de marketing digital")

        # La cápsula debe tener uses >= 1
        caps = memory_store.procedural.list_all()
        marketing_caps = [c for c in caps if "marketing" in c.name.lower()]
        assert len(marketing_caps) >= 1
        assert marketing_caps[0].uses >= 1, f"Expected uses >= 1, got {marketing_caps[0].uses}"
