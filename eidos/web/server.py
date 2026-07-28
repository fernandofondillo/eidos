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
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from eidos import __version__
from eidos.core.engine import EidosCore
from eidos.utils.logging import configure_logging, get_logger
from eidos.web.providers import PROVIDERS, get_provider, list_providers
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
# API Providers + Keys (Fase 6) — gestion .env local + reload en caliente
# ---------------------------------------------------------------------------


@app.get("/api/providers")
async def get_providers() -> dict[str, Any]:
    """Lista de API providers soportados por la UI."""
    return {"providers": list_providers()}


def _env_file_path() -> Path:
    return _project_root / ".env"


def _read_env_keys() -> dict[str, str]:
    """Lee las API keys del archivo .env. Devuelve dict env_var -> valor (o '')."""
    env_path = _env_file_path()
    keys: dict[str, str] = {}
    if not env_path.exists():
        return {p.env_var: "" for p in PROVIDERS}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    # Asegurar que todos los providers estan presentes (aunque vacios)
    for p in PROVIDERS:
        if p.env_var not in keys:
            keys[p.env_var] = ""
    return keys


def _write_env_keys(keys: dict[str, str]) -> None:
    """Escribe las API keys al archivo .env. Solo las conocidas."""
    env_path = _env_file_path()
    lines = ["# API Keys - gestionado por EIDOS UI (boton Settings)"]
    lines.append("# No editar manualmente.")
    lines.append("")
    for p in PROVIDERS:
        val = keys.get(p.env_var, "")
        # Sanitizar: no permitir saltos de linea en el valor
        val = val.replace("\n", "").replace("\r", "").strip()
        lines.append(f"{p.env_var}={val}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.get("/api/config/keys")
async def get_keys() -> dict[str, Any]:
    """Devuelve las API keys configuradas (enmascaradas: solo primeros 8 chars)."""
    keys = _read_env_keys()
    # Enmascarar para la UI: mostrar solo si esta set + primeros 8 chars
    masked: dict[str, dict[str, Any]] = {}
    for p in PROVIDERS:
        val = keys.get(p.env_var, "")
        if val:
            masked[p.id] = {
                "provider": p.name,
                "env_var": p.env_var,
                "set": True,
                "preview": val[:8] + "..." if len(val) > 8 else val,
            }
        else:
            masked[p.id] = {
                "provider": p.name,
                "env_var": p.env_var,
                "set": False,
                "preview": "",
            }
    return {"keys": masked}


@app.post("/api/config/keys")
async def save_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Guarda las API keys en .env y recarga el APIFallbackBackend en caliente.

    Espera: {"keys": {"OPENAI_API_KEY": "sk-...", "ANTHROPIC_API_KEY": "..."}}
    Las keys vacias se ignoran (no se sobreescriben).
    """
    new_keys = payload.get("keys", {})
    if not isinstance(new_keys, dict):
        raise HTTPException(status_code=422, detail="'keys' must be an object")

    # Validar que solo aceptamos env_vars conocidas
    valid_env_vars = {p.env_var for p in PROVIDERS}
    for k in new_keys:
        if k not in valid_env_vars:
            raise HTTPException(status_code=422, detail=f"Unknown env var: {k}")

    # Leer .env actual y actualizar con los nuevos valores no vacios
    current = _read_env_keys()
    updated_count = 0
    for k, v in new_keys.items():
        v = (v or "").strip()
        if v:
            current[k] = v
            updated_count += 1
        # Si v es vacio, no tocamos el existente (para no borrar por error)

    _write_env_keys(current)

    # Recargar en caliente: las nuevas keys se aplican al proximo request
    # via os.environ. APIFallbackBackend lee api_key_env al construirse.
    for k, v in current.items():
        if v:
            os.environ[k] = v

    logger.info("api_keys_updated", count=updated_count)
    return {"updated": True, "count": updated_count, "note": "Keys aplicadas en caliente."}


@app.post("/api/config/keys/clear")
async def clear_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Borra una key especifica del .env. Espera: {"env_var": "OPENAI_API_KEY"}."""
    env_var = payload.get("env_var")
    if not env_var:
        raise HTTPException(status_code=422, detail="'env_var' required")
    valid_env_vars = {p.env_var for p in PROVIDERS}
    if env_var not in valid_env_vars:
        raise HTTPException(status_code=422, detail=f"Unknown env var: {env_var}")

    current = _read_env_keys()
    current[env_var] = ""
    _write_env_keys(current)
    # Quitar de os.environ
    os.environ.pop(env_var, None)
    logger.info("api_key_cleared", env_var=env_var)
    return {"cleared": True, "env_var": env_var}


# ---------------------------------------------------------------------------
# Provider Activo (Fase 6) — seleccionar qué provider usar para pensar
# ---------------------------------------------------------------------------


@app.get("/api/config/active_provider")
async def get_active_provider() -> dict[str, Any]:
    """Devuelve el provider activo actual (o None si usa stub/llama_cpp)."""
    core = get_core()
    api_backend = core.api_backend
    if api_backend is None:
        return {"active": None, "effective_backend": core._effective_backend}
    return {
        "active": {
            "api_type": getattr(api_backend, "_api_type", "openai"),
            "model": getattr(api_backend, "_model", "?"),
            "base_url": getattr(api_backend, "_base_url", "?"),
            "api_key_env": getattr(api_backend, "_api_key_env", "?"),
        },
        "effective_backend": core._effective_backend,
    }


@app.post("/api/config/active_provider")
async def set_active_provider(payload: dict[str, Any]) -> dict[str, Any]:
    """Activa un provider como backend de monólogo en caliente.

    Espera: {"provider_id": "minimax_anthropic"}
    Construye el APIFallbackBackend con base_url, api_key_env, model y
    api_type del provider seleccionado, y lo inyecta en EidosCore.

    Requiere que la API key del provider esté configurada previamente
    (vía POST /api/config/keys).
    """
    provider_id = payload.get("provider_id")
    if not provider_id:
        raise HTTPException(status_code=422, detail="'provider_id' required")

    provider = get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    # Verificar que la API key está configurada
    keys = _read_env_keys()
    api_key = keys.get(provider.env_var, "")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"API key for {provider.name} not configured. Set it first via /api/config/keys.",
        )

    # Asegurar que la key está en os.environ para que APIFallbackBackend la lea
    os.environ[provider.env_var] = api_key

    # Construir el APIFallbackBackend con el api_type correcto
    from eidos.cortex.api_fallback import APIFallbackBackend

    backend = APIFallbackBackend(
        base_url=provider.base_url,
        api_key_env=provider.env_var,
        model=provider.default_model,
        api_type=provider.api_type,
    )

    # Inyectar en el core (activa backend='api' en caliente)
    core = get_core()
    core.set_api_backend(backend)

    logger.info(
        "active_provider_set",
        provider_id=provider_id,
        api_type=provider.api_type,
        model=provider.default_model,
    )
    return {
        "active": True,
        "provider_id": provider_id,
        "provider_name": provider.name,
        "api_type": provider.api_type,
        "model": provider.default_model,
        "note": f"EIDOS ahora piensa con {provider.name} ({provider.default_model}).",
    }


@app.delete("/api/config/active_provider")
async def clear_active_provider() -> dict[str, Any]:
    """Desactiva el provider API y vuelve al backend anterior (stub o llama_cpp)."""
    core = get_core()
    # Para desactivar, reconstruimos el backend con la config original
    # Simplemente ponemos _api_backend a None y el _resolve_backend usará stub
    core._api_backend = None
    # Reconstruir generador con stub
    from eidos.core.monologue import MonologueGenerator

    core._generator = MonologueGenerator(
        backend="stub",
        monologues_dir=core._monologues_dir,
        max_plan_steps=core._max_plan_steps,
    )
    core._effective_backend = "stub"
    logger.info("active_provider_cleared")
    return {"cleared": True, "note": "EIDOS volvió al modo stub."}


# ---------------------------------------------------------------------------
# Model Manager — registrar y descargar Cerebro Local (Fase 6)
# ---------------------------------------------------------------------------


# Estado global de descarga activa (singleton en el proceso)
_download_state: dict[str, Any] = {
    "active": False,
    "model_id": None,
    "received_bytes": 0,
    "total_bytes": 0,
    "error": None,
    "completed": False,
}
_download_lock = threading.Lock()


@app.get("/api/models")
async def list_models() -> dict[str, Any]:
    """Lista los modelos registrados en el ModelManager."""
    core = get_core()
    if core._cortex_hub is None:
        return {"models": [], "cortex_enabled": False}
    mm = core._cortex_hub._mm
    models = [m.to_dict() for m in mm.list_all()]
    return {"models": models, "cortex_enabled": True}


@app.post("/api/models/register")
async def register_default_model(payload: dict[str, Any]) -> dict[str, Any]:
    """Registra el modelo Qwen 2.5 3B por defecto (si no existe)."""
    core = get_core()
    if core._cortex_hub is None:
        raise HTTPException(status_code=503, detail="Cortex Hub not enabled")
    mm = core._cortex_hub._mm

    model_id = payload.get("model_id", "qwen2.5-3b-instruct")
    existing = mm.get(model_id)
    if existing is not None:
        return {"registered": True, "model_id": model_id, "already_existed": True}

    mm.register(
        model_id=model_id,
        name="Qwen2.5-3B-Instruct",
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        format="gguf",
        purpose="monologue",
        quantization="Q4_K_M",
    )
    return {"registered": True, "model_id": model_id, "already_existed": False}


@app.post("/api/models/download")
async def start_download(payload: dict[str, Any]) -> dict[str, Any]:
    """Inicia la descarga de un modelo en background. Devuelve inmediatamente.

    El frontend debe pollear /api/models/download/status para ver el progreso.
    """
    global _download_state
    core = get_core()
    if core._cortex_hub is None:
        raise HTTPException(status_code=503, detail="Cortex Hub not enabled")
    mm = core._cortex_hub._mm

    model_id = payload.get("model_id")
    if not model_id:
        raise HTTPException(status_code=422, detail="'model_id' required")

    info = mm.get(model_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not registered")

    with _download_lock:
        if _download_state["active"]:
            raise HTTPException(status_code=409, detail="Another download is already in progress")
        _download_state = {
            "active": True,
            "model_id": model_id,
            "received_bytes": 0,
            "total_bytes": 0,
            "error": None,
            "completed": False,
        }

    def progress_cb(received: int, total: int) -> None:
        with _download_lock:
            _download_state["received_bytes"] = received
            _download_state["total_bytes"] = total

    def run_download() -> None:
        global _download_state
        try:
            mm.download(model_id, progress_callback=progress_cb)
            with _download_lock:
                _download_state["completed"] = True
                _download_state["active"] = False
            logger.info("model_download_completed", model_id=model_id)
        except Exception as e:
            with _download_lock:
                _download_state["error"] = str(e)
                _download_state["active"] = False
            logger.error("model_download_failed", model_id=model_id, error=str(e))

    thread = threading.Thread(target=run_download, daemon=True, name="model-download")
    thread.start()
    return {"started": True, "model_id": model_id}


@app.get("/api/models/download/status")
async def download_status() -> dict[str, Any]:
    """Devuelve el estado actual de la descarga activa (o la ultima)."""
    with _download_lock:
        state = dict(_download_state)
    # Calcular porcentaje
    if state["total_bytes"] > 0:
        state["percent"] = round(100 * state["received_bytes"] / state["total_bytes"], 1)
    else:
        state["percent"] = 0
    return state


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
