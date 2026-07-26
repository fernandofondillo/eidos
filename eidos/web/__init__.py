"""EIDOS Web Server — Fase 5.

FastAPI app que expone EidosCore via REST + WebSocket.
Sirve el frontend React compilado en producción.

Uso:
    uv run eidos-web                    # arranca servidor en :8765
    uv run eidos-web --port 9000        # puerto custom
    uv run eidos-web --reload           # desarrollo con auto-reload
"""

from eidos.web.server import app, run

__all__ = ["app", "run"]
