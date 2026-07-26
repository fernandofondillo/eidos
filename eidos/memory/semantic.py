"""Capa 3 — Memoria Semántica (Corteza).

Grafo de conocimiento local: hechos, relaciones, identidad del usuario.
Backend: networkx (puro Python) serializado a JSON en data/graph.json.

Estructura del grafo:
- Nodos:   { "id": str, "kind": str, "attrs": {...} }
- Aristas: { "src": str, "dst": str, "predicate": str, "attrs": {...} }

Persistencia: JSON snapshot atómico (write-to-tmp + rename).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidos.memory.base import MemoryLayer
from eidos.utils.logging import get_logger

logger = get_logger(__name__)

# networkx es dependencia nueva en Fase 1.2; lo importamos perezosamente
# para que el paquete importe correctamente incluso si falta (mejor mensaje error).
try:
    import networkx as nx  # type: ignore[import-not-found]
    _HAS_NX = True
except ImportError:
    _HAS_NX = False
    nx = None  # type: ignore[assignment]


class SemanticMemory(MemoryLayer):
    """Capa 3: grafo de conocimiento."""

    layer_name = "semantic"

    def __init__(self, graph_path: Path) -> None:
        if not _HAS_NX:
            raise RuntimeError(
                "networkx no está instalado. Ejecuta: uv add networkx"
            )
        self._graph_path = graph_path
        self._graph: "nx.DiGraph" = nx.DiGraph()
        self._load()

    # ---------------- public API ----------------

    def add_entity(self, entity_id: str, kind: str, attrs: dict[str, Any] | None = None) -> None:
        """Añade o actualiza una entidad (nodo)."""
        if not entity_id or not kind:
            raise ValueError("entity_id and kind are required")
        if entity_id in self._graph:
            # Update attrs preserving edges
            self._graph.nodes[entity_id].update({"kind": kind, **(attrs or {})})
        else:
            self._graph.add_node(entity_id, kind=kind, **(attrs or {}))
        self._save()

    def add_relation(
        self,
        src: str,
        predicate: str,
        dst: str,
        attrs: dict[str, Any] | None = None,
    ) -> None:
        """Añade una relación tipada (arista dirigida).

        Crea los nodos implícitamente si no existen (con kind='unknown').
        """
        if not all([src, predicate, dst]):
            raise ValueError("src, predicate, dst are all required")
        if src not in self._graph:
            self._graph.add_node(src, kind="unknown")
        if dst not in self._graph:
            self._graph.add_node(dst, kind="unknown")
        self._graph.add_edge(src, dst, predicate=predicate, **(attrs or {}))
        self._save()

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        if entity_id not in self._graph:
            return None
        data = dict(self._graph.nodes[entity_id])
        return {"id": entity_id, **data}

    def query_relations(
        self, entity_id: str, direction: str = "out"
    ) -> list[dict[str, Any]]:
        """Devuelve relaciones salientes/entrantes de una entidad."""
        if entity_id not in self._graph:
            return []
        out: list[dict[str, Any]] = []
        if direction in ("out", "both"):
            for src, dst, data in self._graph.out_edges(entity_id, data=True):
                out.append({"src": src, "dst": dst, **data})
        if direction in ("in", "both"):
            for src, dst, data in self._graph.in_edges(entity_id, data=True):
                out.append({"src": src, "dst": dst, **data})
        return out

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Búsqueda lexical simple en IDs y attrs de nodos. (No es vectorial;
        la capa semántica es por grafo. Para recuperación semántica profunda
        usar la capa episódica.)
        """
        q = query.lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for node_id, data in self._graph.nodes(data=True):
            text = (node_id + " " + str(data.get("kind", ""))).lower()
            score = sum(1 for tok in q.split() if tok in text)
            if score > 0:
                scored.append((score, {"id": node_id, **data}))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def store(self, *args: Any, **kwargs: Any) -> Any:
        """API genérica — usar add_entity / add_relation para claridad."""
        if "entity_id" in kwargs:
            return self.add_entity(kwargs["entity_id"], kwargs.get("kind", "unknown"), kwargs.get("attrs"))
        if "src" in kwargs and "dst" in kwargs:
            return self.add_relation(kwargs["src"], kwargs["predicate"], kwargs["dst"], kwargs.get("attrs"))
        raise TypeError("SemanticMemory.store requires entity_id or src/dst")

    def clear(self) -> int:
        n = self._graph.number_of_nodes()
        self._graph.clear()
        self._save()
        return n

    def stats(self) -> dict[str, Any]:
        return {
            "layer": self.layer_name,
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "path": str(self._graph_path),
        }

    # ---------------- persistence ----------------

    def _load(self) -> None:
        if not self._graph_path.exists():
            return
        try:
            data = json.loads(self._graph_path.read_text(encoding="utf-8"))
            for node in data.get("nodes", []):
                self._graph.add_node(node["id"], **node.get("attrs", {"kind": node.get("kind", "unknown")}))
            for edge in data.get("edges", []):
                self._graph.add_edge(
                    edge["src"], edge["dst"],
                    predicate=edge.get("predicate", "related"),
                    **edge.get("attrs", {}),
                )
            logger.info("semantic_graph_loaded", nodes=len(data.get("nodes", [])), edges=len(data.get("edges", [])))
        except Exception as e:
            logger.error("semantic_graph_load_failed", error=str(e))

    def _save(self) -> None:
        """Atomic save: write to .tmp then rename."""
        self._graph_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "nodes": [
                {"id": n, "attrs": dict(d)} for n, d in self._graph.nodes(data=True)
            ],
            "edges": [
                {"src": s, "dst": d, "predicate": data.get("predicate", "related"), "attrs": {k: v for k, v in data.items() if k != "predicate"}}
                for s, d, data in self._graph.edges(data=True)
            ],
        }
        tmp = self._graph_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._graph_path)


__all__ = ["SemanticMemory"]
