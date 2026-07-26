"""Tests del Consolidator — Fase 1.3."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from eidos.core.consolidator import Consolidator
from eidos.core.monologue import Monologue
from eidos.memory.store import MemoryStore
from eidos.utils.persistence import apply_migrations


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    tmp_migrations = tmp_path / "data" / "migrations"
    tmp_migrations.mkdir(parents=True)
    for f in proj_migrations.glob("*.sql"):
        (tmp_migrations / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    config = {
        "memory": {
            "sensory": {"window_size": 30},
            "episodic": {
                "db_path": "data/eidos.db",
                "embedding_dim": 64,
                "max_events": 100,
            },
            "semantic": {"graph_path": "data/graph.json"},
            "procedural": {
                "capsules_dir": "data/capsules",
                "default_ttl_days": 7,
            },
        }
    }
    return MemoryStore.from_config(config, tmp_path)


@pytest.fixture
def monologues_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data" / "monologues"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def consolidator(memory_store: MemoryStore, monologues_dir: Path) -> Consolidator:
    return Consolidator(
        memory=memory_store,
        db_path=memory_store.db_path,
        monologues_dir=monologues_dir,
        interval_sec=60,
    )


# ---------------------------------------------------------------------------
# run_once — pasos individuales
# ---------------------------------------------------------------------------


class TestConsolidatorRunOnce:
    def test_run_once_returns_metrics(self, consolidator: Consolidator) -> None:
        result = consolidator.run_once(kind="manual")
        assert result["kind"] == "manual"
        assert "items_processed" in result
        assert "duration_ms" in result
        assert "details" in result
        # Detalles deben contener las 5 claves esperadas
        expected_keys = {
            "sensory_promoted",
            "monologues_indexed",
            "outcomes_inferred",
            "capsules_expired",
            "episodic_pruned_check",
        }
        assert set(result["details"].keys()) == expected_keys

    def test_run_once_logs_run_to_db(self, consolidator: Consolidator) -> None:
        consolidator.run_once(kind="manual")
        runs = consolidator.recent_runs(limit=5)
        assert len(runs) == 1
        assert runs[0]["kind"] == "manual"

    def test_run_once_idempotent_no_crash(self, consolidator: Consolidator) -> None:
        consolidator.run_once()
        consolidator.run_once()
        consolidator.run_once()
        runs = consolidator.recent_runs(limit=10)
        assert len(runs) == 3


# ---------------------------------------------------------------------------
# Paso: compactación sensory → episódica
# ---------------------------------------------------------------------------


class TestSensoryPromotion:
    def test_high_confidence_response_promoted(
        self, memory_store: MemoryStore, consolidator: Consolidator
    ) -> None:
        # Simular una respuesta con confianza alta
        memory_store.sensory.store(
            kind="response",
            content="respuesta importante",
            metadata={"confidence": 0.85, "route": "respond_direct"},
        )
        # Antes de consolidar, episódica está vacía
        assert memory_store.episodic.stats()["total"] == 0

        consolidator.run_once()
        # Ahora debe tener al menos 1 evento promovido
        assert memory_store.episodic.stats()["total"] >= 1

    def test_low_confidence_response_not_promoted(
        self, memory_store: MemoryStore, consolidator: Consolidator
    ) -> None:
        memory_store.sensory.store(
            kind="response",
            content="respuesta menor",
            metadata={"confidence": 0.3, "route": "respond_direct"},
        )
        consolidator.run_once()
        # No debe promoverse (threshold=0.6 por defecto)
        assert memory_store.episodic.stats()["total"] == 0

    def test_user_input_not_promoted(
        self, memory_store: MemoryStore, consolidator: Consolidator
    ) -> None:
        # Solo se promueven 'response', no 'user_input'
        memory_store.sensory.store(
            kind="user_input",
            content="pregunta del usuario",
            metadata={"confidence": 0.95},
        )
        consolidator.run_once()
        assert memory_store.episodic.stats()["total"] == 0


# ---------------------------------------------------------------------------
# Paso: indexación de monólogos huérfanos
# ---------------------------------------------------------------------------


class TestOrphanMonologueIndexing:
    def test_orphan_monologue_indexed(
        self, memory_store: MemoryStore, consolidator: Consolidator, monologues_dir: Path
    ) -> None:
        # Crear un monólogo en disco SIN indexar
        m = Monologue(
            input_summary="orphan input",
            observation="obs",
            hypothesis="hyp",
            plan=["s1"],
            risk="none",
            confidence=0.7,
            backend="stub",
        )
        # Escribir el JSON directamente (sin pasar por metacognitive.store)
        json_path = monologues_dir / f"{m.id}.json"
        json_path.write_text(m.model_dump_json(indent=2), encoding="utf-8")

        # Verificar que NO está indexado
        assert memory_store.metacognitive.get(m.id) is None

        result = consolidator.run_once()
        assert result["details"]["monologues_indexed"] >= 1

        # Ahora debe estar indexado
        indexed = memory_store.metacognitive.get(m.id)
        assert indexed is not None
        assert indexed["input_summary"] == "orphan input"

    def test_already_indexed_not_reprocessed(
        self, memory_store: MemoryStore, consolidator: Consolidator, monologues_dir: Path
    ) -> None:
        m = Monologue(
            input_summary="already indexed",
            observation="obs",
            hypothesis="hyp",
            plan=["s1"],
            risk="none",
            confidence=0.7,
            backend="stub",
        )
        # Indexar primero
        memory_store.metacognitive.store(m, route_type="respond_direct")
        # Y también escribir el JSON
        json_path = monologues_dir / f"{m.id}.json"
        json_path.write_text(m.model_dump_json(indent=2), encoding="utf-8")

        result = consolidator.run_once()
        # No debe re-indexar
        assert result["details"]["monologues_indexed"] == 0


# ---------------------------------------------------------------------------
# Paso: expiración de cápsulas por TTL
# ---------------------------------------------------------------------------


class TestCapsuleExpiry:
    def test_expired_capsule_deleted(
        self, memory_store: MemoryStore, consolidator: Consolidator
    ) -> None:
        import sqlite3
        from datetime import datetime, timedelta, timezone

        rec = memory_store.procedural.store(
            name="Expiring",
            version="1.0.0",
            description="",
            content={},
            ttl_days=1,
        )
        # Forzar created_at a 30 días atrás
        old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = sqlite3.connect(memory_store.db_path)
        conn.execute("UPDATE capsules SET created_at = ? WHERE id = ?", (old, rec.id))
        conn.commit()
        conn.close()

        assert memory_store.procedural.get(rec.id) is not None

        result = consolidator.run_once()
        assert result["details"]["capsules_expired"] >= 1
        assert memory_store.procedural.get(rec.id) is None

    def test_favorite_capsule_not_expired(
        self, memory_store: MemoryStore, consolidator: Consolidator
    ) -> None:
        import sqlite3
        from datetime import datetime, timedelta, timezone

        rec = memory_store.procedural.store(
            name="Favorite",
            version="1.0.0",
            description="",
            content={},
            ttl_days=1,
            favorite=True,
        )
        old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = sqlite3.connect(memory_store.db_path)
        conn.execute("UPDATE capsules SET created_at = ? WHERE id = ?", (old, rec.id))
        conn.commit()
        conn.close()

        consolidator.run_once()
        # Las favoritas NUNCA expiran
        assert memory_store.procedural.get(rec.id) is not None


# ---------------------------------------------------------------------------
# Paso: inferencia de outcomes
# ---------------------------------------------------------------------------


class TestOutcomeInference:
    def test_outcome_inferred_from_rewards(
        self, memory_store: MemoryStore, consolidator: Consolidator, monologues_dir: Path
    ) -> None:
        from eidos.core.motivation import MotivationModule

        # Crear monólogo sin outcome
        m = Monologue(
            input_summary="input test",
            observation="obs",
            hypothesis="hyp",
            plan=["s1"],
            risk="none",
            confidence=0.7,
            backend="stub",
        )
        memory_store.metacognitive.store(m, route_type="respond_direct")
        # Escribir JSON también (consolidator lo necesita para indexar)
        json_path = monologues_dir / f"{m.id}.json"
        json_path.write_text(m.model_dump_json(indent=2), encoding="utf-8")

        # Registrar rewards positivos asociados
        mm = MotivationModule(db_path=memory_store.db_path)
        mm.reward_capsule_use("cap-1", monologue_id=m.id)
        mm.reward_capsule_use("cap-2", monologue_id=m.id)

        # Antes de consolidar, outcome es NULL
        assert memory_store.metacognitive.get(m.id)["outcome"] is None

        consolidator.run_once()
        # Después, outcome debe estar inferido
        indexed = memory_store.metacognitive.get(m.id)
        assert indexed["outcome"] in ("positive", "negative", "neutral")


# ---------------------------------------------------------------------------
# Lifecycle: start/stop
# ---------------------------------------------------------------------------


class TestConsolidatorLifecycle:
    def test_start_and_stop(self, consolidator: Consolidator) -> None:
        consolidator.start()
        assert consolidator.is_running() is True
        consolidator.stop(timeout=2.0)
        assert consolidator.is_running() is False

    def test_double_start_idempotent(self, consolidator: Consolidator) -> None:
        consolidator.start()
        consolidator.start()  # no debe lanzar
        assert consolidator.is_running() is True
        consolidator.stop(timeout=2.0)

    def test_stop_without_start_noop(self, consolidator: Consolidator) -> None:
        consolidator.stop()  # no debe lanzar
        assert consolidator.is_running() is False

    def test_interval_minimum_enforced(self, memory_store: MemoryStore, monologues_dir: Path) -> None:
        # interval_sec=5 debe ser elevado a 30 (mínimo)
        c = Consolidator(
            memory=memory_store,
            db_path=memory_store.db_path,
            monologues_dir=monologues_dir,
            interval_sec=5,
        )
        assert c._interval == 30


# ---------------------------------------------------------------------------
# Integración E2E con EidosCore
# ---------------------------------------------------------------------------


class TestEidosCoreWithMotivationAndConsolidator:
    def test_response_includes_reward_delta(self, memory_store: MemoryStore, monologues_dir: Path) -> None:
        from eidos.core.engine import EidosCore
        from eidos.core.motivation import MotivationModule

        mm = MotivationModule(db_path=memory_store.db_path, procedural=memory_store.procedural)
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
            motivation=mm,
            consolidator=None,  # sin consolidator en este test
            auto_start_consolidator=False,
        )
        resp = core.think_and_respond("hola EIDOS")
        assert hasattr(resp, "reward_delta")
        # Primer input neutro → reward_delta=0 (no hay racha completa todavía)
        assert resp.reward_delta == 0.0

    def test_negative_input_triggers_negative_reward(
        self, memory_store: MemoryStore
    ) -> None:
        from eidos.core.engine import EidosCore
        from eidos.core.motivation import MotivationModule

        mm = MotivationModule(db_path=memory_store.db_path, procedural=memory_store.procedural)
        core = EidosCore(
            monologue_backend="stub",
            confidence_threshold=0.4,
            monologues_dir=None,
            memory=memory_store,
            motivation=mm,
            consolidator=None,
            auto_start_consolidator=False,
        )
        resp = core.think_and_respond("no, eso está mal")
        assert resp.reward_delta < 0.0

    def test_shutdown_stops_consolidator(
        self, memory_store: MemoryStore, monologues_dir: Path
    ) -> None:
        from eidos.core.engine import EidosCore
        from eidos.core.motivation import MotivationModule

        mm = MotivationModule(db_path=memory_store.db_path, procedural=memory_store.procedural)
        cons = Consolidator(
            memory=memory_store,
            db_path=memory_store.db_path,
            monologues_dir=monologues_dir,
            interval_sec=300,
        )
        core = EidosCore(
            monologue_backend="stub",
            monologues_dir=None,
            memory=memory_store,
            motivation=mm,
            consolidator=cons,
            auto_start_consolidator=True,
        )
        assert cons.is_running() is True
        core.shutdown()
        assert cons.is_running() is False
