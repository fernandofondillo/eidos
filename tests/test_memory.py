"""Tests de las 5 capas de memoria — Fase 1.2."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidos.utils.persistence import apply_migrations


# ---------------------------------------------------------------------------
# Fixtures compartidas
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """DB con migraciones aplicadas (schema inicial completo)."""
    db = tmp_path / "test.db"
    # Aplicar migraciones del proyecto
    proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
    apply_migrations(db, proj_migrations)
    return db


@pytest.fixture
def capsules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "capsules"
    d.mkdir(exist_ok=True)
    return d


@pytest.fixture
def graph_path(tmp_path: Path) -> Path:
    return tmp_path / "graph.json"


# ---------------------------------------------------------------------------
# Capa 1 — SensoryMemory
# ---------------------------------------------------------------------------


class TestSensoryMemory:
    def test_store_and_recent(self, db_path: Path) -> None:
        from eidos.memory.sensory import SensoryMemory

        sm = SensoryMemory(db_path, window_size=10)
        rid = sm.store("user_input", "hola")
        assert rid > 0
        recent = sm.recent()
        assert len(recent) == 1
        assert recent[0]["content"] == "hola"
        assert recent[0]["kind"] == "user_input"

    def test_window_size_pruning(self, db_path: Path) -> None:
        from eidos.memory.sensory import SensoryMemory

        sm = SensoryMemory(db_path, window_size=3)
        for i in range(5):
            sm.store("user_input", f"msg-{i}")
        assert len(sm.recent()) == 3
        # Más recientes primero
        contents = [r["content"] for r in sm.recent()]
        assert "msg-4" in contents
        assert "msg-3" in contents
        assert "msg-2" in contents
        assert "msg-0" not in contents  # pruned

    def test_persistence_across_instances(self, db_path: Path) -> None:
        from eidos.memory.sensory import SensoryMemory

        sm1 = SensoryMemory(db_path, window_size=10)
        sm1.store("user_input", "persisted-msg")
        del sm1

        sm2 = SensoryMemory(db_path, window_size=10)
        recent = sm2.recent()
        assert any(r["content"] == "persisted-msg" for r in recent)

    def test_metadata_persisted(self, db_path: Path) -> None:
        from eidos.memory.sensory import SensoryMemory

        sm = SensoryMemory(db_path, window_size=10)
        sm.store("user_input", "hi", metadata={"foo": "bar"})
        recent = sm.recent()
        assert recent[0]["metadata"] == {"foo": "bar"}

    def test_clear(self, db_path: Path) -> None:
        from eidos.memory.sensory import SensoryMemory

        sm = SensoryMemory(db_path, window_size=10)
        sm.store("user_input", "a")
        sm.store("user_input", "b")
        deleted = sm.clear()
        assert deleted == 2
        assert sm.recent() == []

    def test_stats(self, db_path: Path) -> None:
        from eidos.memory.sensory import SensoryMemory

        sm = SensoryMemory(db_path, window_size=5)
        sm.store("user_input", "x")
        s = sm.stats()
        assert s["layer"] == "sensory"
        assert s["window_size"] == 5
        assert s["buffered"] == 1
        assert s["total_persisted"] == 1


# ---------------------------------------------------------------------------
# Capa 2 — EpisodicMemory
# ---------------------------------------------------------------------------


class TestEpisodicMemory:
    def test_store_and_recent(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        em = EpisodicMemory(db_path, embedding_dim=64, max_events=100)
        eid = em.store("interaction", "Hello EIDOS world")
        assert eid > 0
        recent = em.recent(limit=5)
        assert len(recent) == 1
        assert "Hello EIDOS world" in recent[0]["content"]

    def test_search_returns_relevant(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        em = EpisodicMemory(db_path, embedding_dim=64, max_events=100)
        em.store("interaction", "EIDOS es un proyecto de IA cognitiva")
        em.store("interaction", "Recetas de cocina italiana con pasta")
        em.store("interaction", "Arquitectura de sistemas multi-agente")

        # Búsqueda con keywords presentes en el primer evento
        results = em.search("EIDOS IA cognitiva", top_k=2)
        assert len(results) > 0
        assert any("EIDOS" in r["content"] for r in results)

    def test_search_with_min_score(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        em = EpisodicMemory(db_path, embedding_dim=64, max_events=100)
        em.store("interaction", "completely different content about cooking")
        # Si forzamos min_score alto, esperamos menos resultados
        results = em.search("quantum physics astrophysics", top_k=5, min_score=0.99)
        assert len(results) == 0

    def test_importance_validation(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        em = EpisodicMemory(db_path, embedding_dim=64)
        with pytest.raises(ValueError):
            em.store("x", "y", importance=1.5)
        with pytest.raises(ValueError):
            em.store("x", "y", importance=-0.1)

    def test_lru_pruning(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        em = EpisodicMemory(db_path, embedding_dim=64, max_events=3)
        em.store("interaction", "low-1", importance=0.1)
        em.store("interaction", "low-2", importance=0.1)
        em.store("interaction", "low-3", importance=0.1)
        em.store("interaction", "high-1", importance=0.9)
        em.store("interaction", "high-2", importance=0.9)

        recent = em.recent(limit=10)
        # Solo 3 sobreviven
        assert len(recent) == 3
        contents = " ".join(r["content"] for r in recent)
        assert "high-1" in contents
        assert "high-2" in contents
        # Al menos uno de los "low" debería haberse podado
        assert "low-1" not in contents or "low-2" not in contents or "low-3" not in contents

    def test_stub_embed_deterministic(self) -> None:
        from eidos.memory.episodic import stub_embed

        v1 = stub_embed("hello world", dim=64)
        v2 = stub_embed("hello world", dim=64)
        assert v1 == v2

    def test_stub_embed_normalized(self) -> None:
        import math

        from eidos.memory.episodic import stub_embed

        v = stub_embed("hello world foo bar", dim=64)
        norm = math.sqrt(sum(x * x for x in v))
        assert 0.99 <= norm <= 1.01

    def test_stats(self, db_path: Path) -> None:
        from eidos.memory.episodic import EpisodicMemory

        em = EpisodicMemory(db_path, embedding_dim=64, max_events=50)
        em.store("x", "y")
        s = em.stats()
        assert s["layer"] == "episodic"
        assert s["total"] == 1
        assert s["embedding_dim"] == 64


# ---------------------------------------------------------------------------
# Capa 3 — SemanticMemory
# ---------------------------------------------------------------------------


class TestSemanticMemory:
    def test_add_entity_and_get(self, graph_path: Path) -> None:
        from eidos.memory.semantic import SemanticMemory

        sm = SemanticMemory(graph_path)
        sm.add_entity("eidos", "project", {"version": "0.1"})
        e = sm.get_entity("eidos")
        assert e is not None
        assert e["kind"] == "project"
        assert e["version"] == "0.1"

    def test_add_relation_creates_implicit_nodes(self, graph_path: Path) -> None:
        from eidos.memory.semantic import SemanticMemory

        sm = SemanticMemory(graph_path)
        sm.add_relation("eidos", "uses", "python")
        assert sm.get_entity("eidos") is not None
        assert sm.get_entity("python") is not None
        rels = sm.query_relations("eidos", direction="out")
        assert len(rels) == 1
        assert rels[0]["predicate"] == "uses"
        assert rels[0]["dst"] == "python"

    def test_persistence_across_instances(self, graph_path: Path) -> None:
        from eidos.memory.semantic import SemanticMemory

        sm1 = SemanticMemory(graph_path)
        sm1.add_entity("x", "thing")
        sm1.add_relation("x", "related", "y")
        del sm1

        sm2 = SemanticMemory(graph_path)
        assert sm2.get_entity("x") is not None
        assert sm2.get_entity("y") is not None
        assert len(sm2.query_relations("x")) == 1

    def test_search_lexical(self, graph_path: Path) -> None:
        from eidos.memory.semantic import SemanticMemory

        sm = SemanticMemory(graph_path)
        sm.add_entity("eidos_project", "project")
        sm.add_entity("random_thing", "thing")
        results = sm.search("eidos")
        assert any(r["id"] == "eidos_project" for r in results)

    def test_clear(self, graph_path: Path) -> None:
        from eidos.memory.semantic import SemanticMemory

        sm = SemanticMemory(graph_path)
        sm.add_entity("a", "thing")
        sm.add_entity("b", "thing")
        n = sm.clear()
        assert n == 2
        assert sm.stats()["nodes"] == 0

    def test_stats(self, graph_path: Path) -> None:
        from eidos.memory.semantic import SemanticMemory

        sm = SemanticMemory(graph_path)
        sm.add_entity("a", "thing")
        sm.add_entity("b", "thing")
        sm.add_relation("a", "r", "b")
        s = sm.stats()
        assert s["layer"] == "semantic"
        assert s["nodes"] == 2
        assert s["edges"] == 1


# ---------------------------------------------------------------------------
# Capa 4 — ProceduralMemory
# ---------------------------------------------------------------------------


class TestProceduralMemory:
    def test_store_and_get(self, db_path: Path, capsules_dir: Path) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir, default_ttl_days=7)
        rec = pm.store(
            name="Rust Auditor",
            version="1.0.0",
            description="Audits Rust code",
            content={"rules": ["no unsafe"]},
        )
        assert rec.id
        assert rec.name == "Rust Auditor"
        fetched = pm.get(rec.id)
        assert fetched is not None
        assert fetched.name == "Rust Auditor"

    def test_capsule_file_persisted(self, db_path: Path, capsules_dir: Path) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir)
        rec = pm.store(
            name="Test Capsule",
            version="0.1.0",
            description="",
            content={"key": "value"},
        )
        # El archivo .eidos debe existir
        files = list(capsules_dir.glob("*.eidos"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["name"] == "Test Capsule"
        assert data["content"]["key"] == "value"

    def test_mark_used_increments_counter(self, db_path: Path, capsules_dir: Path) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir)
        rec = pm.store(name="C", version="1.0.0", description="", content={})
        assert rec.uses == 0

        pm.mark_used(rec.id)
        pm.mark_used(rec.id)
        fetched = pm.get(rec.id)
        assert fetched is not None
        assert fetched.uses == 2
        assert fetched.last_used is not None

    def test_set_favorite(self, db_path: Path, capsules_dir: Path) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir)
        rec = pm.store(name="Fav", version="1.0.0", description="", content={})
        pm.set_favorite(rec.id, True)
        fetched = pm.get(rec.id)
        assert fetched is not None
        assert fetched.favorite is True

    def test_delete(self, db_path: Path, capsules_dir: Path) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir)
        rec = pm.store(name="Del", version="1.0.0", description="", content={})
        ok = pm.delete(rec.id)
        assert ok is True
        assert pm.get(rec.id) is None
        # Archivo también debe borrarse
        files = list(capsules_dir.glob("*.eidos"))
        assert len(files) == 0

    def test_ttl_expiry(self, db_path: Path, capsules_dir: Path) -> None:
        from datetime import datetime, timedelta, timezone

        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir, default_ttl_days=1)
        rec = pm.store(name="Expiring", version="1.0.0", description="", content={}, ttl_days=1)
        # Manipular created_at a 2 días atrás en DB para simular expiración
        import sqlite3

        old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE capsules SET created_at = ? WHERE id = ?", (old_ts, rec.id))
        conn.commit()
        conn.close()

        expired = pm.expire_due()
        assert rec.id in expired

    def test_favorite_never_expires(self, db_path: Path, capsules_dir: Path) -> None:
        from datetime import datetime, timedelta, timezone
        import sqlite3

        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir, default_ttl_days=1)
        rec = pm.store(name="Favorite", version="1.0.0", description="", content={}, ttl_days=1, favorite=True)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE capsules SET created_at = ? WHERE id = ?", (old_ts, rec.id))
        conn.commit()
        conn.close()

        expired = pm.expire_due()
        assert rec.id not in expired

    def test_clear_keeps_favorites(self, db_path: Path, capsules_dir: Path) -> None:
        from eidos.memory.procedural import ProceduralMemory

        pm = ProceduralMemory(db_path, capsules_dir)
        pm.store(name="Normal", version="1.0.0", description="", content={})
        fav = pm.store(name="Fav", version="1.0.0", description="", content={})
        pm.set_favorite(fav.id, True)

        deleted = pm.clear()
        assert deleted == 1
        remaining = pm.list_all()
        assert len(remaining) == 1
        assert remaining[0].favorite is True


# ---------------------------------------------------------------------------
# Capa 5 — MetacognitiveMemory
# ---------------------------------------------------------------------------


class TestMetacognitiveMemory:
    def test_store_and_get(self, db_path: Path) -> None:
        from eidos.core.monologue import Monologue
        from eidos.memory.metacognitive import MetacognitiveMemory

        mm = MetacognitiveMemory(db_path)
        m = Monologue(
            input_summary="test input",
            observation="obs",
            hypothesis="hyp",
            plan=["step1", "step2"],
            risk="none",
            confidence=0.8,
            backend="stub",
        )
        mm.store(m, route_type="respond_direct")

        fetched = mm.get(m.id)
        assert fetched is not None
        assert fetched["input_summary"] == "test input"
        assert fetched["route_type"] == "respond_direct"
        assert fetched["confidence"] == 0.8
        assert fetched["plan"] == ["step1", "step2"]

    def test_recent(self, db_path: Path) -> None:
        from eidos.core.monologue import Monologue
        from eidos.memory.metacognitive import MetacognitiveMemory

        mm = MetacognitiveMemory(db_path)
        for i in range(3):
            m = Monologue(
                input_summary=f"input-{i}",
                observation="o",
                hypothesis="h",
                plan=["s"],
                risk="none",
                confidence=0.5,
                backend="stub",
            )
            mm.store(m)
        recent = mm.recent(limit=10)
        assert len(recent) == 3

    def test_search_by_route(self, db_path: Path) -> None:
        from eidos.core.monologue import Monologue
        from eidos.memory.metacognitive import MetacognitiveMemory

        mm = MetacognitiveMemory(db_path)
        for route in ["respond_direct", "search_memory", "respond_direct"]:
            m = Monologue(
                input_summary="x",
                observation="o",
                hypothesis="h",
                plan=["s"],
                risk="none",
                confidence=0.6,
                backend="stub",
            )
            mm.store(m, route_type=route)
        rd = mm.search_by_route("respond_direct")
        assert len(rd) == 2
        sm = mm.search_by_route("search_memory")
        assert len(sm) == 1

    def test_low_confidence(self, db_path: Path) -> None:
        from eidos.core.monologue import Monologue
        from eidos.memory.metacognitive import MetacognitiveMemory

        mm = MetacognitiveMemory(db_path)
        for conf in [0.3, 0.4, 0.8, 0.9]:
            m = Monologue(
                input_summary="x",
                observation="o",
                hypothesis="h",
                plan=["s"],
                risk="none",
                confidence=conf,
                backend="stub",
            )
            mm.store(m)
        low = mm.low_confidence(threshold=0.5)
        assert len(low) == 2
        assert all(r["confidence"] < 0.5 for r in low)

    def test_set_outcome(self, db_path: Path) -> None:
        from eidos.core.monologue import Monologue
        from eidos.memory.metacognitive import MetacognitiveMemory

        mm = MetacognitiveMemory(db_path)
        m = Monologue(
            input_summary="x",
            observation="o",
            hypothesis="h",
            plan=["s"],
            risk="none",
            confidence=0.7,
            backend="stub",
        )
        mm.store(m)
        mm.set_outcome(m.id, "user_satisfied")
        fetched = mm.get(m.id)
        assert fetched is not None
        assert fetched["outcome"] == "user_satisfied"

    def test_stats(self, db_path: Path) -> None:
        from eidos.core.monologue import Monologue
        from eidos.memory.metacognitive import MetacognitiveMemory

        mm = MetacognitiveMemory(db_path)
        for conf, route in [(0.3, "search_memory"), (0.8, "respond_direct")]:
            m = Monologue(
                input_summary="x",
                observation="o",
                hypothesis="h",
                plan=["s"],
                risk="none",
                confidence=conf,
                backend="stub",
            )
            mm.store(m, route_type=route)
        s = mm.stats()
        assert s["layer"] == "metacognitive"
        assert s["total"] == 2
        assert s["by_route"]["respond_direct"] == 1
        assert s["by_route"]["search_memory"] == 1


# ---------------------------------------------------------------------------
# MemoryStore — fachada
# ---------------------------------------------------------------------------


class TestMemoryStore:
    def test_from_config_initializes_all_layers(self, tmp_path: Path) -> None:
        from eidos.memory.store import MemoryStore

        # Setup: copiar migraciones a tmp
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
        store = MemoryStore.from_config(config, tmp_path)
        assert store.sensory is not None
        assert store.episodic is not None
        assert store.semantic is not None
        assert store.procedural is not None
        assert store.metacognitive is not None

    def test_stats_returns_all_layers(self, tmp_path: Path) -> None:
        from eidos.memory.store import MemoryStore

        proj_migrations = Path(__file__).resolve().parent.parent / "data" / "migrations"
        tmp_migrations = tmp_path / "data" / "migrations"
        tmp_migrations.mkdir(parents=True)
        for f in proj_migrations.glob("*.sql"):
            (tmp_migrations / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

        config = {"memory": {"episodic": {"db_path": "data/eidos.db"}}}
        store = MemoryStore.from_config(config, tmp_path)
        s = store.stats()
        assert set(s.keys()) == {"sensory", "episodic", "semantic", "procedural", "metacognitive"}
