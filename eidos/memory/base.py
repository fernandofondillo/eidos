"""Interfaz base para las 5 capas de memoria cognitiva de EIDOS.

Toda capa implementa MemoryLayer con store/retrieve/clear mínimo.
Las capas específicas añaden métodos propios (vectorial, grafo, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MemoryLayer(ABC):
    """Contrato común para todas las capas de memoria.

    Cada capa es responsable de su propia persistencia y de su
    configuración (paths, dimensiones, etc.).
    """

    layer_name: str = "abstract"

    @abstractmethod
    def store(self, *args: Any, **kwargs: Any) -> Any:
        """Persiste un evento/hecho/cápsula en esta capa."""
        ...

    @abstractmethod
    def clear(self) -> int:
        """Vacía la capa. Devuelve número de elementos eliminados."""
        ...

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """Estadísticas básicas para diagnostico/UI."""
        ...


__all__ = ["MemoryLayer"]
