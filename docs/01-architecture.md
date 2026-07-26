# Arquitectura de EIDOS — Visión General

> Documento vivo. Se actualiza cada fase.

## 1. Principios fundacionales

1. **Neuro-simbólico** — lo neuronal propone (LLM pequeño genera hipótesis), lo simbólico valida (Pydantic schemas, AST parsing, reglas).
2. **Cognición profunda pero eficiente** — modelos 1.5B–3B fine-tuneados para razonamiento, no fuerza bruta. JSON schema forzado compensa la debilidad del modelo.
3. **Cero dependencias pesadas** — no Ollama, no LM Studio, no Docker para el usuario final. Todo nativo y portable.
4. **Vibe coding** — modular, configuración-driven, documentado para no-expertos.
5. **Trazabilidad total** — cada decisión deja un monólogo persistente. EIDOS puede explicar por qué hizo X.

## 2. Componentes

### 2.1 Núcleo Cognitivo Profundo (Fase 1)

El `EidosCore` orquesta el flujo:

```
user_input → MonologueGenerator → Monologue (Pydantic, JSON forzado)
           → ActionRouter       → Route (RESPOND | SEARCH_MEM | CLARIFY | CORTEX | MESH | SAFETY_BLOCK)
           → (NLG/acción)       → Response
```

**Monólogo Interno**: Cada pensamiento tiene el esquema rígido:

- `observation`: qué percibe EIDOS
- `hypothesis`: hipótesis principal
- `plan`: pasos ordenados (máx 5, configurable)
- `risk`: riesgo identificado
- `confidence`: 0.0–1.0; < umbral → pedir aclaración

**Backends**:
- `stub` (Fase 1): determinista, sin GPU, para desarrollo.
- `llama_cpp` (Fase 2): Qwen2.5-3B local con JSON mode / GBNF.
- `api` (Fase 2.3): fallback externo.

### 2.2 Memoria Cognitiva de 5 Capas (Fase 1.2)

| Capa | Nombre | Backend | Propósito |
|------|--------|---------|-----------|
| 1 | Sensorial | `deque` + SQLite | Contexto inmediato (últimos 50 eventos) |
| 2 | Episódica | sqlite-vec (v1) → LanceDB (upgrade) | "Qué pasó y cuándo" — vectorial |
| 3 | Semántica | networkx + JSON | Grafo de conocimiento — hechos, relaciones, identidad |
| 4 | Procedimental | SQLite + `.eidos` files | Cápsulas y herramientas creadas/aprendidas |
| 5 | Metacognitiva | SQLite `monologue_index` | "Memoria sobre memoria" — indexa monólogos pasados |

### 2.3 Cortex Hub — Sentidos Periféricos (Fase 2)

Gestor de LLMs locales GGUF/ONNX. El núcleo decide qué "sentido" activar (visión, lectura profunda, código) y el Cortex Hub lo carga en VRAM/RAM solo durante la inferencia. **Singleton virtual en MESH**: solo el Primario posee modelos cargados; los Workers piden inferencia vía bus.

### 2.4 Génesis de Cápsulas (Fase 3)

Si el usuario pide "conviértete en experto en auditoría de Rust" y no existe la cápsula, EIDOS la **crea**:

1. Genera un `.eidos` (ontología + reglas + herramientas + tono) — Pydantic-validado.
2. Lo guarda en Memoria Procedimental.
3. Se auto-inyecta la especialización en milisegundos.
4. **TTL + scoring**: cápsula no-favorita expira si no se usa en `ttl_days`.

**Seguridad**: el Tool Sandbox (3.1) jamás hace `exec()` directo. AST parsing + whitelist de imports + aislamiento por proceso con `resource.setrlimit()`.

### 2.5 EIDOS MESH (Fase 4)

Multi-instancia cooperativa en un mismo dispositivo:

- **Transporte**: Sockets UNIX (POSIX) / named pipes (Windows). JSON-RPC 2.0 ligero. Upgrade path: Redis embebido si escala.
- **Leader Election**: lockfile atómico (`O_CREAT|O_EXCL`) + PID. Heartbeat 2s; re-elección a los 6s.
- **Arbitraje de recursos**: solo el Primario posee Cortex Hub activo. Workers piden `resource_token` (TTL 30s) para cargar modelo.
- **Memoria compartida**: SQLite WAL mode (single-writer/multi-reader) + bus pub/sub `MEMORY_UPDATE` para caché local.

## 3. Decisiones técnicas clave

| Decisión | Justificación |
|----------|---------------|
| Python 3.11+ | Velocidad de desarrollo, ecosistema IA, legibilidad "vibe coding". |
| uv | Lockfile determinista, rápido, moderno. |
| Pydantic v2 | Schemas rígidos para modelos pequeños. |
| sqlite-vec v1 | Un único `.db` file = máxima portabilidad pendrive. LanceDB como upgrade. |
| Sockets UNIX v1 | Cero dependencias. Redis embebido como upgrade path. |
| Qwen2.5-3B-Instruct | JSON mode nativo, buena relación razonamiento/RAM. |
| Tauri v2 (Fase 5) | Empaquetado real cross-platform (Mac/Win/Linux/iOS/Android). |

## 4. Anti-patrones prohibidos

- `exec()` / `eval()` directo en Tool Sandbox.
- Cargar modelo LLM en Worker sin `resource_token`.
- Monólogo en texto libre (sin schema) — SIEMPRE JSON forzado.
- Dependencia de Ollama / LM Studio / Docker para el usuario final.
- Avanzar de fase sin tests pasando.

## 5. Roadmap de fases

- ✅ **Fase 1.1**: Core Engine + MonologueGenerator (stub). Tests verdes.
- ✅ **Fase 1.2**: 5 capas de memoria (SQLite + sqlite-vec + networkx + .eidos). 74 tests.
- ✅ **Fase 1.3**: Motivación intrínseca (3 drivers) + consolidador background. 108 tests.
- ✅ **Fase 2**: Cortex Hub (ModelManager + LlamaCppBackend + Embeddings + APIFallback + PrivacyFilter). 158 tests.
- ✅ **Fase 3**: Génesis de cápsulas + Tool Sandbox (defense-in-depth) + EvolutionLoop. 229 tests.
- ✅ **Fase 4**: EIDOS MESH (sockets UNIX + leader election + arbitrator + MeshCoordinator). 279 tests.
- ✅ **Fase 5**: UI Web (FastAPI + React) + Tauri v2 + despliegue cross-platform. 298 tests.
- 🎉 **PROYECTO COMPLETO** — 7/7 fases selladas.

## 6. Memoria cognitiva (Fase 1.2) — detalle de implementación

### Tablas SQLite (migración 0001)

```sql
sensory_events     -- Capa 1: (id, ts, kind, content, metadata)
episodic_events    -- Capa 2: (id, ts, kind, content, embedding, importance, metadata)
                   -- + virtual table episodic_vec (vec0) si sqlite-vec disponible
capsules           -- Capa 4: (id, name, version, file_path, ttl_days, uses, favorite, ...)
monologue_index    -- Capa 5: (id, ts, input_summary, hypothesis, plan, risk, confidence, route_type, outcome)
schema_migrations  -- bookkeeping de migraciones
```

### Embeddings stub

```python
def stub_embed(text: str, dim: int = 256) -> list[float]:
    """Bag-of-words hasheado + L2 normalize. Determinista, sin GPU.
    Fase 2 lo sustituye por embeddings del Cortex Hub."""
```

### TTL de cápsulas

- Cada cápsula nace con `ttl_days` (default 7).
- `last_used` se actualiza cada vez que se invoca.
- Expiración: si `favorite == False` y `(now - last_used or created_at).days >= ttl_days`.
- El consolidador (Fase 1.3) llamará `expire_due()` y las eliminará.
- `favorite == True` → nunca expira.

### Degradación graceful

- **sqlite-vec no instalado** → EpisodicMemory degrada a bruteforce cosine en Python. Más lento pero funcional. Log de aviso al arranque.
- **networkx no instalado** → SemanticMemory lanza RuntimeError con instrucciones claras al instanciarse (no silence failure).
- **DB corrupta** → migraciones idempotentes, no rompen el arranque.

## 7. Motivación + Consolidación (Fase 1.3) — detalle de implementación

### Reward signal

Cada interacción pasa por el `MotivationModule` antes y después del monólogo. Los 3 drivers se combinan linealmente:

```python
reward_delta = (
    observe_user_input(user_input)       # +0.3 streak / -0.5 negative
  + observe_confidence(confidence)       # +0.3 si sube >avg+0.1
  + reward_capsule_use(capsule_id)       # +0.4 por invocación
)
```

Persistencia: tabla `reward_events(id, ts, monologue_id, driver, delta, total, metadata)`. Cada reward es auditable.

### Consolidador (hilo daemon)

```python
class Consolidator:
    def run_once(self, kind="manual") -> dict:
        return {
            "sensory_promoted": self._compact_sensory_to_episodic(),
            "monologues_indexed": self._index_orphan_monologues(),
            "outcomes_inferred": self._infer_outcomes(),
            "capsules_expired": self._expire_capsules(),
            "episodic_pruned_check": self._check_episodic_overflow(),
        }
```

- Thread daemon: muere con el proceso principal, sin necesidad de stop explícito.
- `stop(timeout)` hace join limpio para shutdown controlado.
- `run_once(kind="manual")` expuesto vía CLI para consolidación on-demand.
- Cada run se persiste en `consolidation_runs` con métricas detalladas.

### Inferencia de outcomes (metacognición)

Para cada monologue en `monologue_index` con `outcome IS NULL`, el consolidador:
1. Mira los `reward_events` en los 5 min posteriores al monologue.
2. Suma los deltas por driver.
3. Etiqueta: `positive` (sum > +0.2) / `negative` (sum < -0.2) / `neutral` (resto).

Esto permite a la capa metacognitiva responder preguntas como *"¿qué tipo de rutas (route_type) tienden a generar outcomes negativos?"* — base del aprendizaje por refuerzo en futuras fases.

## 8. Cortex Hub (Fase 2) — detalle de implementación

### Backends del MonologueGenerator

| Backend | Cuándo se usa | Requiere |
|---------|---------------|----------|
| `stub` | Desarrollo sin GPU, tests | Nada |
| `llama_cpp` | Modelo GGUF local cargado | `llama-cpp-python` + modelo en `/models` |
| `api` | Fallback externo (opt-in) | API key en env var |
| `auto` | Selección automática | CortexHub + degradación graceful a stub |

`MonologueGenerator` ahora acepta `backend_instance` para inyectar un backend ya construido (útil cuando CortexHub ha cargado el modelo).

### LlamaCppBackend — JSON forzado con GBNF

El backend usa `LlamaGrammar.from_string(_MONOLOGUE_GBNF)` para forzar al modelo a producir JSON válido según el schema del Monologue. Si el modelo genera JSON inválido:
1. Se reintenta (máx 3 intentos, bajando `temperature` en cada reintento).
2. Tras N reintentos, lanza `RuntimeError` (EidosCore captura y degrada a stub en modo `auto`).

### PrivacyFilter

8 patrones regex en orden específico (URL_CREDENTIALS → IBAN → CREDIT_CARD → EMAIL → DNI_ES → IPV4 → PHONE_INTL → PHONE_ES). Cada match se reemplaza por `[REDACTED_<TYPE>_<N>]`. Patrones custom inyectables para dominios específicos.

### CortexHub — lock singleton-virtual-ready

```python
hub.try_acquire_lock(role="primary", ttl_sec=60.0)  # fcntl.flock local en Fase 2
# En Fase 4: resource_token MESH distribuido, MISMA API
```

El lock se adquiere antes de cargar cualquier modelo en VRAM. TTL evita deadlocks si el proceso muere sin liberar. En Fase 4 se sustituirá la implementación sin cambiar la API pública.

### EpisodicMemory con embedder inyectable

```python
em = EpisodicMemory(db_path, embedder=hub.get_embedder())  # real
em = EpisodicMemory(db_path)                                # stub (default)
```

Cuando CortexHub tiene un modelo de embeddings READY, EpisodicMemory usa embeddings reales (dim 384 típica para BGE-small). Si no, degrada a `stub_embed` (dim 256). La tabla `vec0` se crea con la dim del embedder al primer arranque.

## 9. Génesis de Cápsulas + Tool Sandbox (Fase 3)

### ToolSandbox — defense-in-depth

```python
sandbox = ToolSandbox(timeout_sec=5, mem_limit_mb=256, cpu_limit_sec=2)
result = sandbox.run_code(code, entry="main", args={})
```

3 capas:

1. **AST validation** (`_ASTValidator`):
   - Whitelist de imports: math, statistics, json, re, datetime, collections, itertools, functools, typing, dataclasses, enum, etc.
   - Rechaza: `exec`, `eval`, `compile`, `__import__`, `open`, `globals`, `locals`, `vars`, `input`, `breakpoint`.
   - Rechaza attribute access a `__builtins__`, `__subclasses__`, `__globals__`, `__code__`, etc.
   - Permite dunders legítimos: `__init__`, `__str__`, `__len__`, `__iter__`, `__call__`, etc.

2. **Subprocess aislado**:
   - `stdin=DEVNULL`, `stdout=PIPE`, `stderr=PIPE`.
   - `timeout` agresivo (default 5s).
   - Environment restringido: solo `PATH`.
   - Wrapper Python que carga el código + llama `entry(**args)`.
   - Builtins peligrosos filtrados del namespace del subprocess.

3. **Resource limits (POSIX)**:
   - `RLIMIT_CPU` (default 2s).
   - `RLIMIT_AS` (default 256MB).
   - `RLIMIT_FSIZE` (1MB).
   - Best-effort: en macOS RLIMIT_AS no siempre funciona, pero el timeout y la CPU limit siguen activos.

### CapsuleForge — pipeline de génesis

```python
forge = CapsuleForge(db_path, procedural, backend=StubForgeBackend(), sandbox=ToolSandbox())
draft, decision = forge.forge("experto en Kubernetes")
# decision ∈ {AUTO_APPROVED, PENDING_APPROVAL, REJECTED}
```

Reglas de auto-aprobación (neuro-simbólico):

```python
def _should_auto_approve(draft):
    if draft.genesis_confidence < 0.85: return False
    if not draft.smoke_test_passed: return False
    for tool in draft.tools:
        if tool.name.lower() in HIGH_RISK_TOOL_NAMES:
            return False  # exec_command, shell, delete, format, rm, fork_bomb
    return True
```

Persistencia dual:
- `capsule_drafts` (migración 0004): todos los drafts con status (pending, approved, rejected, auto_approved).
- `capsules` (migración 0001, Fase 1.2): cápsulas activas tras aprobación.

### EvolutionLoop — detección + promoción

```python
evo = EvolutionLoop(forge, procedural, auto_forge=True)
evo.process_turn(user_input, monologue)  # detecta y forja si procede
evo.check_promotions()  # promueve cápsulas populares a favoritas
```

Patrones NL de detección (regex):

- `conviértete en experto en X`
- `necesito que seas experto en X`
- `crea una cápsula para X`
- `actúa como experto en X`

Promoción a favorita (background):

- `uses >= 3` (configurable `PROMOTION_USES_THRESHOLD`)
- `last_used` dentro de las últimas 24h (`PROMOTION_WINDOW_HOURS`)
- No es ya favorita
- Las favoritas nunca expiran por TTL

### Tablas SQLite (migración 0004)

```sql
capsule_drafts(
    id TEXT PRIMARY KEY,
    requested_by TEXT,         -- 'user' | 'auto_evolution'
    request_input TEXT,        -- petición NL original
    name, version, description,
    ontology JSON, rules JSON, tone JSON, tools JSON,
    genesis_confidence REAL,
    smoke_test_passed INTEGER,
    smoke_test_output TEXT,
    status TEXT,               -- 'pending' | 'approved' | 'rejected' | 'auto_approved'
    created_at, decided_at,
    parent_capsule_id TEXT,    -- genealogía
    metadata JSON
)
```

## 10. EIDOS MESH (Fase 4) — detalle de implementación

### Componentes

| Componente | Archivo | Rol |
|-----------|---------|-----|
| protocol | `eidos/mesh/protocol.py` | JSON-RPC 2.0 adaptado + Pydantic schemas |
| transport | `eidos/mesh/transport.py` | Sockets UNIX (POSIX), server y cliente |
| election | `eidos/mesh/election.py` | Lockfile atómico + heartbeat anti split-brain |
| bus | `eidos/mesh/bus.py` | Pub/sub + request/response, entrega local + remota |
| arbitrator | `eidos/mesh/arbitrator.py` | Resource tokens con TTL anti-deadlock |
| coordinator | `eidos/mesh/coordinator.py` | Facade unificada |

### Leader Election (2 mecanismos anti split-brain)

```python
# 1. Lockfile atómico (POSIX O_CREAT|O_EXCL)
fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
# Operación atómica del SO: solo un proceso gana.

# 2. Heartbeat cada 2s
if time.time() - last_heartbeat > 6.0:  # leader_timeout_sec
    # Re-elección: borrar lockfile stale si PID muerto, intentar de nuevo
    election._try_reelection()
```

### Resource Tokens (arbitraje)

```python
# Worker pide recurso al Leader vía RPC
token = mesh.acquire_resource('cortex', ttl_sec=30)
# → si soy Leader: local directo
# → si soy Worker: send_request_to_leader('acquire_token', ...)

# TTL anti-deadlock: si Worker muere, token expira a los 30s
arb.expire_due()  # llamado periódicamente por el consolidador

# Liberación explícita
mesh.release_resource(token.token_id)
# → si Worker muere sin liberar: release_all_for_holder() en GOODBYE handler
```

### CortexHub refactorizado (misma API)

```python
# Fase 2: fcntl local
hub = CortexHub(model_manager=mm)

# Fase 4: resource_token MESH distribuido
hub = CortexHub(model_manager=mm, mesh_coordinator=coord)

# Misma API pública:
hub.try_acquire_lock(role="primary", ttl_sec=60.0)  # → bool
hub.release_lock()
hub.has_lock()
```

### Tablas SQLite (migración 0005)

```sql
mesh_nodes(
    id TEXT PRIMARY KEY,       -- UUID de la instancia
    pid INTEGER, hostname, socket_path,
    role TEXT,                 -- 'leader' | 'worker' | 'candidate'
    status TEXT,               -- 'alive' | 'dead' | 'leaving'
    last_heartbeat, started_at, metadata
)

resource_tokens(
    token_id TEXT PRIMARY KEY,
    resource TEXT,             -- 'cortex' | 'memory_write' | 'sandbox'
    holder_node_id TEXT,
    acquired_at, expires_at,   -- TTL
    released_at,               -- NULL hasta liberación
    metadata
)
```

### Tests E2E

`tests/test_mesh_coordinator.py` crea dos coordinators reales con sockets UNIX y verifica:
- Leader election (uno gana, otro es worker).
- HELLO registration (worker se registra con leader).
- Resource acquisition (worker pide token vía RPC al leader).
- Concurrent acquire denied (segundo token para mismo recurso → None).
- Stats y lifecycle (start/stop idempotente).

## 11. UI Web + Despliegue Cross-Platform (Fase 5)

### Arquitectura 3 capas

```
┌─────────────────────────────────────────────────┐
│              EIDOS.app / .exe / .AppImage       │
│                                                 │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │  Tauri v2    │  │  Python sidecar         │  │
│  │  (Rust)      │──│  (FastAPI + EidosCore)  │  │
│  │  WebKit UI   │  │  localhost:8765         │  │
│  └──────────────┘  └─────────────────────────┘  │
│         ↕ HTTP / WebSocket                      │
│  ┌─────────────────────────────────────────────┐│
│  │  React UI (ui/dist/)                        ││
│  │  Chat + Monologue + Memory + Capsules +    ││
│  │  MeshMap + RewardChart + Evolution         ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### Backend — FastAPI (eidos/web/)

| Archivo | Rol |
|---------|-----|
| `server.py` | App FastAPI + endpoints REST + WebSocket + static mount |
| `schemas.py` | Pydantic models (contrato frontend↔backend) |

Endpoints:
- REST: health, chat, stats, capsules (list/forge/approve/reject), mesh/status, motivation, evolution, config (get/put)
- WebSocket: `/ws/chat` — chat bidireccional con monologue streaming

Sirve frontend compilado desde `ui/dist/` en producción. CORS abierto para desarrollo (Vite en :5173).

### Frontend — React + Vite + TypeScript (ui/)

| Componente | Función |
|-----------|---------|
| `Header` | Estado global: versión, backend, WS connection, MESH role |
| `ChatPanel` | Input + mensajes historicos, badges de route/backend/confidence/reward |
| `MonologueViewer` | Monologue JSON en vivo (observation, hypothesis, plan, risk, confidence) |
| `MemoryStatsPanel` | 5 capas con métricas (refresh cada 5s) |
| `CapsulesManager` | Forge input + drafts pendientes + cápsulas activas |
| `MeshMap` | Topología visual Leader↔Worker + tokens activos |
| `RewardChart` | Total + desglose por driver + mini timeline de rewards recientes |
| `EvolutionPanel` | Stats autoevolución (total, favoritas, candidatas) |

Hooks:
- `useEidosApi` — fetch REST con auto-refresh cada 5s
- `useEidosWebSocket` — conexión WS con reconnect automático + fallback a REST

Stack: Vite 5, React 18, TypeScript 5, Tailwind CSS 3 (dark theme).

### Tauri v2 (desktop/)

Configuración completa para empaquetado nativo:
- `tauri.conf.json` — bundle targets: app, dmg, msi, deb, appimage
- `src/main.rs` — lanza Python sidecar via `tauri_plugin_shell`
- `Cargo.toml` — dependencias Tauri v2

### Empaquetado Python standalone

Para producción, el backend Python se compila a binario standalone:

```bash
# PyOxidizer (recomendado)
pyoxidizer build --release
# Output: binario nativo con Python embebido + todas las dependencias

# Nuitka (alternativa)
python -m nuitka --standalone --onefile --include-package=eidos eidos/web/server.py
```

### Despliegue portable SSD/Pendrive

```
SSD/Pendrive
└── EIDOS/
    ├── EIDOS.app/            # macOS (.app dentro de .dmg)
    ├── EIDOS.exe             # Windows (.msi)
    ├── EIDOS.AppImage        # Linux
    ├── bin/
    │   └── eidos-server      # Python compilado standalone
    ├── config/
    │   └── eidos.yaml        # config editable por el usuario
    └── data/                 # memoria cognitiva del usuario (portable)
        ├── eidos.db          # SQLite (5 capas)
        ├── graph.json        # grafo semántico
        ├── monologues/       # trazas metacognitivas
        ├── capsules/         # .eidos files
        └── migrations/       # SQL versionado
```

El usuario conecta el SSD a cualquier Mac/Win/Linux, hace doble clic en EIDOS, y su mente artificial está lista con toda su memoria cognitiva intacta.

### Tests del web server

`tests/test_web.py` (19 tests) cubre:
- REST: health, chat, stats, capsules (CRUD), mesh/status, motivation, evolution, config
- WebSocket: chat con monologue streaming, ping/pong, error handling
- Usa `httpx.AsyncClient` con ASGI transport (sin puerto real)
- `pytest-asyncio` en modo auto para tests async
