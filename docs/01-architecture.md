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
- ⏳ Fase 1.2: 5 capas de memoria.
- ⏳ Fase 1.3: Motivación intrínseca + consolidación background.
- ⏳ Fase 2: Cortex Hub (Qwen2.5-3B local, llama-cpp-python).
- ⏳ Fase 3: Génesis de cápsulas + Tool Sandbox.
- ⏳ Fase 4: EIDOS MESH (sockets UNIX + leader election + arbitraje).
- ⏳ Fase 5: UI Tauri v2 + empaquetado cross-platform.
