"""Servidor FastAPI de EIDOS — Fase 5.

Expone EidosCore via REST + WebSocket. Sirve el frontend React
compilado en producción (ui/dist/).

Endpoints REST:
    GET  /api/health              — health check
    POST /api/chat                — chat síncrono (sin streaming)
    GET  /api/stats               — 5 capas de memoria
    GET  /api/capsules            — drafts + cápsulas activas
    POST /api/capsules/forge      — forjar nueva cápsula
    POST /api/capsules/approve    — aprobar draft
    POST /api/capsules/reject     — rechazar draft
    GET  /api/mesh/status         — estado del enjambre
    GET  /api/motivation          — reward signal
    GET  /api/evolution           — evolution stats
    GET  /api/config              — leer config
    PUT  /api/config              — actualizar config

WebSocket:
    WS   /ws/chat                 — chat bidireccional con monólogo en vivo

Estáticos:
    GET  /                        — frontend React (si ui/dist/ existe)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from eidos import __version__
from eidos.core.engine import EidosCore
from eidos.utils.logging import configure_logging, get_logger
from eidos.web.schemas import (
    ApproveRequest,
    ChatRequest,
    ChatResponse,
    EvolutionResponse,
    ForgeRequest,
    HealthResponse,
    MeshStatusResponse,
    MotivationResponse,
    StatsResponse,
    WSIncoming,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Globals — el EidosCore se construye al arrancar
# ---------------------------------------------------------------------------

_core: EidosCore | None = None
_config: dict[str, Any] = {}
_project_root: Path = Path(__file__).resolve().parent.parent.parent


def get_core() -> EidosCore:
    """Devuelve la instancia singleton de EidosCore."""
    global _core
    if _core is None:
        raise RuntimeError("EidosCore not initialized. Call init_core() first.")
    return _core


def init_core(config: dict[str, Any], project_root: Path) -> None:
    """Inicializa el EidosCore global. Llamar al arrancar el server."""
    global _core, _config, _project_root
    _config = config
    _project_root = project_root

    # Reutilizar la lógica del CLI para construir el core
    from eidos.cli import build_core

    configure_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        format=config.get("logging", {}).get("format", "json"),
    )
    _core = build_core(config, project_root, start_consolidator=True)
    logger.info("web_core_initialized", backend=_core._effective_backend)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EIDOS — Entidad Cognitiva Autónoma",
    description="API web del núcleo cognitivo EIDOS. Mente + memoria + motivación + sentidos + autoevolución + enjambre.",
    version=__version__,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — en dev, Vite corre en :5173 y necesita acceder a :8765
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev: cualquier origen; prod: servir desde mismo origen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    core = get_core()
    return HealthResponse(
        status="ok",
        version=__version__,
        backend=core._effective_backend,
        mesh_enabled=core.mesh is not None,
    )


# ---------------------------------------------------------------------------
# Chat (síncrono)
# ---------------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Procesa un mensaje del usuario y devuelve la respuesta completa."""
    core = get_core()
    try:
        resp = core.think_and_respond(req.message, context=req.context)
    except Exception as e:
        logger.error("web_chat_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Cargar el monologue completo: primero de disco (si persist), luego del generador
    monologue_data: dict[str, Any] | None = None
    if core._monologues_dir is not None:
        mono_file = core._monologues_dir / f"{resp.monologue_id}.json"
        if mono_file.exists():
            try:
                monologue_data = json.loads(mono_file.read_text(encoding="utf-8"))
            except Exception:
                pass
    # Fallback: regenerar el monologue desde el generador (determinista en stub)
    if monologue_data is None:
        try:
            mono = core._generator.generate(req.message, context=req.context)
            monologue_data = mono.model_dump(mode="json")
        except Exception:
            pass

    return ChatResponse(
        text=resp.text,
        monologue_id=resp.monologue_id,
        route_type=resp.route_type,
        confidence=resp.confidence,
        reward_delta=resp.reward_delta,
        monologue_backend=resp.monologue_backend,
        memory_context=resp.memory_context,
        evolution_event=resp.evolution_event,
        monologue=monologue_data,
    )


# ---------------------------------------------------------------------------
# Stats — 5 capas de memoria
# ---------------------------------------------------------------------------


@app.get("/api/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    core = get_core()
    if core._memory is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    s = core._memory.stats()
    return StatsResponse(**s)


# ---------------------------------------------------------------------------
# Capsules
# ---------------------------------------------------------------------------


@app.get("/api/capsules")
async def list_capsules() -> dict[str, Any]:
    core = get_core()
    if core._memory is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=core._memory.db_path,
        procedural=core._memory.procedural,
        backend=StubForgeBackend(),
    )
    drafts = forge.list_drafts()
    active = [c.to_dict() for c in core._memory.procedural.list_all()]
    return {"drafts": drafts, "active": active}


@app.post("/api/capsules/forge")
async def forge_capsule(req: ForgeRequest) -> dict[str, Any]:
    core = get_core()
    if core._memory is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    from eidos.core.forge import CapsuleForge, StubForgeBackend
    from eidos.core.sandbox import ToolSandbox

    forge = CapsuleForge(
        db_path=core._memory.db_path,
        procedural=core._memory.procedural,
        backend=StubForgeBackend(),
        sandbox=ToolSandbox(),
    )
    draft, decision = forge.forge(req.request, force_pending=req.force_pending)
    return {
        "draft": draft.model_dump(),
        "decision": decision.value,
    }


@app.post("/api/capsules/approve")
async def approve_capsule(req: ApproveRequest) -> dict[str, Any]:
    core = get_core()
    if core._memory is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=core._memory.db_path,
        procedural=core._memory.procedural,
        backend=StubForgeBackend(),
    )
    ok = forge.approve(req.draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found or not pending")
    return {"approved": True, "draft_id": req.draft_id}


@app.post("/api/capsules/reject")
async def reject_capsule(req: ApproveRequest) -> dict[str, Any]:
    core = get_core()
    if core._memory is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=core._memory.db_path,
        procedural=core._memory.procedural,
        backend=StubForgeBackend(),
    )
    ok = forge.reject(req.draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"rejected": True, "draft_id": req.draft_id}


# ---------------------------------------------------------------------------
# Mesh status
# ---------------------------------------------------------------------------


@app.get("/api/mesh/status", response_model=MeshStatusResponse)
async def mesh_status() -> MeshStatusResponse:
    core = get_core()
    if core.mesh is None:
        return MeshStatusResponse(enabled=False)
    s = core.mesh.stats()
    return MeshStatusResponse(
        enabled=True,
        node_id=s["node_id"],
        role=s["role"],
        leader_id=s.get("leader_id"),
        socket=s.get("socket"),
        peers=s.get("peers", 0),
        arbitrator=s.get("arbitrator"),
    )


# ---------------------------------------------------------------------------
# Motivation
# ---------------------------------------------------------------------------


@app.get("/api/motivation", response_model=MotivationResponse)
async def motivation() -> MotivationResponse:
    core = get_core()
    if core._motivation is None:
        raise HTTPException(status_code=503, detail="Motivation not initialized")
    s = core._motivation.stats()
    recent = core._motivation.recent_rewards(limit=20)
    return MotivationResponse(
        session_total_reward=s["session_total_reward"],
        by_driver=s["by_driver"],
        confidence_window_size=s["confidence_window_size"],
        satisfaction_streak=s["satisfaction_streak"],
        satisfaction_window=s["satisfaction_window"],
        recent_rewards=recent,
    )


# ---------------------------------------------------------------------------
# Evolution
# ---------------------------------------------------------------------------


@app.get("/api/evolution", response_model=EvolutionResponse)
async def evolution() -> EvolutionResponse:
    core = get_core()
    if core._evolution_loop is None:
        raise HTTPException(status_code=503, detail="Evolution loop not initialized")
    s = core._evolution_loop.stats()
    return EvolutionResponse(**s)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    return _config


@app.put("/api/config")
async def update_config(config: dict[str, Any]) -> dict[str, Any]:
    """Actualiza config/eidos.yaml. Requiere reinicio del server para aplicar."""
    global _config
    config_path = _project_root / "config" / "eidos.yaml"
    try:
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        _config = config
        return {"updated": True, "note": "Restart server to apply changes."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# WebSocket — chat bidireccional con monólogo en vivo
# ---------------------------------------------------------------------------


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    """WebSocket para chat en vivo.

    Cliente envía: {"type": "chat", "message": "...", "context": "..."}
    Server responde:
      {"type": "monologue", "data": {...}}  — el monologue generado
      {"type": "response", "data": {...}}   — la respuesta final
      {"type": "error", "error": "..."}
    """
    await ws.accept()
    core = get_core()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = WSIncoming.model_validate_json(raw)
            except Exception as e:
                await ws.send_text(json.dumps({"type": "error", "error": f"Invalid message: {e}"}))
                continue

            if msg.type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue

            if msg.type != "chat" or not msg.message:
                await ws.send_text(json.dumps({"type": "error", "error": "Expected type='chat' with 'message'"}))
                continue

            try:
                resp = core.think_and_respond(msg.message, context=msg.context)

                # Cargar monologue completo: de disco o regenerado
                monologue_data: dict[str, Any] | None = None
                if core._monologues_dir is not None:
                    mono_file = core._monologues_dir / f"{resp.monologue_id}.json"
                    if mono_file.exists():
                        try:
                            monologue_data = json.loads(mono_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                if monologue_data is None:
                    try:
                        mono = core._generator.generate(msg.message, context=msg.context)
                        monologue_data = mono.model_dump(mode="json")
                    except Exception:
                        pass

                # Enviar monologue primero
                await ws.send_text(json.dumps({
                    "type": "monologue",
                    "data": monologue_data or {},
                }))

                # Luego la response completa
                await ws.send_text(json.dumps({
                    "type": "response",
                    "data": {
                        "text": resp.text,
                        "monologue_id": resp.monologue_id,
                        "route_type": resp.route_type,
                        "confidence": resp.confidence,
                        "reward_delta": resp.reward_delta,
                        "monologue_backend": resp.monologue_backend,
                        "memory_context": resp.memory_context,
                        "evolution_event": resp.evolution_event,
                    },
                }))
            except Exception as e:
                logger.error("ws_chat_error", error=str(e))
                await ws.send_text(json.dumps({"type": "error", "error": str(e)}))
    except WebSocketDisconnect:
        logger.info("ws_client_disconnected")
    except Exception as e:
        logger.error("ws_error", error=str(e))


# ---------------------------------------------------------------------------
# Static frontend — servir React compilado
# ---------------------------------------------------------------------------


def _mount_frontend() -> None:
    """Sirve el frontend React desde ui/dist/ si existe."""
    ui_dist = _project_root / "ui" / "dist"
    if ui_dist.exists():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="frontend")
        logger.info("web_frontend_mounted", path=str(ui_dist))
    else:
        @app.get("/", response_class=HTMLResponse)
        async def index_fallback() -> HTMLResponse:
            return HTMLResponse(
                """<html><body style="font-family: sans-serif; padding: 40px; background: #1a1a2e; color: #eee;">
                <h1>🧠 EIDOS Web API</h1>
                <p>Backend funcionando. Frontend no compilado.</p>
                <p>Para desarrollo: <code>cd ui && npm install && npm run dev</code></p>
                <p>Para producción: <code>cd ui && npm run build</code> (luego reinicia el server)</p>
                <p>Docs API: <a href="/api/docs" style="color: #6db33f">/api/docs</a></p>
                </body></html>"""
            )


# Montar al final (después de todas las rutas API)
_mount_frontend()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """Arranca el servidor web. Punto de entrada para `eidos-web`."""
    import argparse

    parser = argparse.ArgumentParser(description="EIDOS Web Server")
    parser.add_argument("--port", type=int, default=8765, help="Puerto (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload (desarrollo)")
    args = parser.parse_args()

    # Cargar config y inicializar core
    from eidos.cli import load_config

    config = load_config(_project_root / "config" / "eidos.yaml")
    init_core(config, _project_root)

    import uvicorn

    print(f"\n  🧠 EIDOS Web Server v{__version__}")
    print(f"  → http://{args.host}:{args.port}")
    print(f"  → API docs: http://{args.host}:{args.port}/api/docs")
    print(f"  → Backend: {get_core()._effective_backend}")
    print(f"  → Mesh: {'ON' if get_core().mesh else 'OFF'}")
    print()

    uvicorn.run(
        "eidos.web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    run()
