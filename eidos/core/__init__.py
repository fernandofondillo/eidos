"""Core cognitivo de EIDOS.

Componentes:
- engine:    orquesta monólogo → acción → respuesta.
- monologue: generador de CoT estructurado (JSON schema forzado).
- router:    decide la ruta de acción tras el monólogo.
"""

from eidos.core.engine import EidosCore
from eidos.core.monologue import Monologue, MonologueGenerator
from eidos.core.router import ActionRouter, Route, RouteType

__all__ = [
    "EidosCore",
    "Monologue",
    "MonologueGenerator",
    "ActionRouter",
    "Route",
    "RouteType",
]
