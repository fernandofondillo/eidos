"""Tests de memoria semántica — extracción y persistencia de hechos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidos.memory.semantic import SemanticMemory


@pytest.fixture
def graph_path(tmp_path: Path) -> Path:
    return tmp_path / "graph.json"


@pytest.fixture
def semantic(graph_path: Path) -> SemanticMemory:
    return SemanticMemory(graph_path=graph_path)


class TestSemanticMemoryExtraction:
    def test_semantic_memory_extracts_facts(self, semantic: SemanticMemory) -> None:
        """Cuando el usuario dice su nombre, debe guardarse en el grafo."""
        semantic.add_entity("usuario", "person", {"name": "Fernando"})
        semantic.add_relation("usuario", "tiene_nombre", "fernando")

        entity = semantic.get_entity("usuario")
        assert entity is not None
        assert entity["name"] == "Fernando"

        rels = semantic.query_relations("usuario", direction="out")
        name_rels = [r for r in rels if r.get("predicate") == "tiene_nombre"]
        assert len(name_rels) > 0
        assert name_rels[0]["dst"] == "fernando"

    def test_semantic_memory_extracts_profession(self, semantic: SemanticMemory) -> None:
        """Profesión debe guardarse como relación."""
        semantic.add_entity("usuario", "person", {"profession": "desarrollador"})
        semantic.add_relation("usuario", "tiene_profesion", "desarrollador")

        rels = semantic.query_relations("usuario", direction="out")
        prof_rels = [r for r in rels if r.get("predicate") == "tiene_profesion"]
        assert len(prof_rels) > 0
        assert prof_rels[0]["dst"] == "desarrollador"

    def test_semantic_memory_extracts_project(self, semantic: SemanticMemory) -> None:
        """Proyecto debe guardarse como relación."""
        semantic.add_entity("suplemento nutricional", "project")
        semantic.add_relation("usuario", "tiene_proyecto", "suplemento nutricional")

        rels = semantic.query_relations("usuario", direction="out")
        proj_rels = [r for r in rels if r.get("predicate") == "tiene_proyecto"]
        assert len(proj_rels) > 0
        assert "suplemento" in proj_rels[0]["dst"]


class TestSemanticMemoryPersistence:
    def test_semantic_memory_persists_between_sessions(self, graph_path: Path) -> None:
        """El grafo debe cargarse desde disk al iniciar."""
        # Sesión 1: guardar hecho
        sem1 = SemanticMemory(graph_path=graph_path)
        sem1.add_entity("usuario", "person", {"name": "Fernando"})
        sem1.add_relation("usuario", "tiene_nombre", "fernando")
        # graph.json se guarda automáticamente en add_entity/add_relation

        # Sesión 2: nueva instancia carga desde disco
        sem2 = SemanticMemory(graph_path=graph_path)
        entity = sem2.get_entity("usuario")
        assert entity is not None
        assert entity["name"] == "Fernando"

        rels = sem2.query_relations("usuario", direction="out")
        name_rels = [r for r in rels if r.get("predicate") == "tiene_nombre"]
        assert len(name_rels) > 0
        assert name_rels[0]["dst"] == "fernando"

    def test_graph_json_exists_after_save(self, graph_path: Path) -> None:
        """El archivo graph.json debe existir tras guardar."""
        sem = SemanticMemory(graph_path=graph_path)
        sem.add_entity("test", "thing")
        assert graph_path.exists()

        data = json.loads(graph_path.read_text(encoding="utf-8"))
        assert "nodes" in data
        assert len(data["nodes"]) > 0
