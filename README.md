# 🧠 EIDOS

> **Entidad Cognitiva Autónoma, Profunda y Enjambre.**
> Una mente artificial modular, portable, privada y cooperativa.

[![Phase](https://img.shields.io/badge/phase-1.1--Core%20%26%20Monologue-blue)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/uv-0.11+-purple.svg)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)]()

EIDOS no es un chatbot. Es un **organismo digital** con:

- **Cognición Profunda** — núcleo neuro-simbólico con monólogo interno estructurado (Chain-of-Thought en JSON forzado), persistente y auditable.
- **Memoria de 5 capas** — sensorial, episódica, semántica, procedimental y metacognitiva.
- **Génesis de Cápsulas** — auto-especialización al vuelo: si no existe la experticia, EIDOS la crea como archivo `.eidos` y se la auto-inyecta.
- **EIDOS MESH** — multi-instancia cooperativa en un mismo dispositivo, con auto-organización y arbitraje de VRAM/RAM.
- **100% portable** — vive en un SSD/Pendrive. Cero dependencias pesadas para el usuario final (no Ollama, no LM Studio, no Docker).

---

## 📐 Estado del proyecto

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1.1   | Estructura + Core Engine + MonologueGenerator (stub) | ✅ |
| 1.2   | 5 capas de memoria (SQLite + sqlite-vec + grafo JSON) | ✅ |
| 1.3   | Motivación intrínseca + consolidación background | ✅ |
| **2** | **Cortex Hub — modelos GGUF locales + API fallback con PrivacyFilter** | ✅ **Esta release** |
| 3     | Génesis dinámica de cápsulas + Tool Sandbox | ⏳ Próxima |
| 4     | EIDOS MESH — enjambre y cooperación | ⏳ |
| 5     | UI Tauri v2 + empaquetado cross-platform | ⏳ |

---

## 🚀 Quickstart (Fase 2)

### Requisitos

- **Python 3.11+** (probado en 3.11 y 3.12)
- **[uv](https://docs.astral.sh/uv/)** — gestor de dependencias moderno y rápido
- macOS Apple Silicon (entorno primario), Linux o Windows

### Instalación

```bash
# 1. Clonar
git clone https://github.com/EIDOS-project/eidos.git
cd eidos

# 2. Sincronizar dependencias con uv (crea .venv automáticamente)
uv sync

# 3. (Opcional) instalar dependencias de desarrollo
uv sync --extra dev
```

### Uso

```bash
# REPL interactivo — monólogo + memoria + reward signal + consolidador + CortexHub
uv run eidos

# Una sola consulta (sin arrancar consolidador)
uv run eidos --once "¿Qué es EIDOS?" --no-consolidator

# Estadísticas de las 5 capas de memoria
uv run eidos stats

# Métricas del reward signal (motivación intrínseca)
uv run eidos motivation

# Ejecutar consolidación manual inmediata
uv run eidos consolidate

# Historial de ejecuciones del consolidador
uv run eidos runs

# Gestión de modelos GGUF (Fase 2)
uv run eidos models list
uv run eidos models download <model_id>
uv run eidos models delete <model_id>

# Estado del CortexHub (Fase 2)
uv run eidos cortex status
uv run eidos cortex verify
uv run eidos cortex privacy-test "Mi email es test@example.com"

# Con config custom
uv run eidos --config /path/to/eidos.yaml

# Versión
uv run eidos --version
```

### Activar Cortex Hub (modelos locales)

1. Compila `llama-cpp-python` con Metal (macOS Apple Silicon):
   ```bash
   CMAKE_ARGS="-DGGML_METAL=on" uv sync --extra cortex
   ```

2. Habilita el Cortex Hub en `config/eidos.yaml`:
   ```yaml
   cortex:
     enabled: true
     models_dir: "models"
   core:
     monologue_backend: "auto"  # usa llama_cpp si hay modelo, si no stub
   ```

3. Registra y descarga un modelo (programáticamente o vía config):
   ```bash
   uv run eidos models download qwen2.5-3b-instruct
   ```

### Tests

```bash
uv run pytest -v
```

---

## 🏗️ Arquitectura (Fase 1.1)

```
            ┌─────────────────────────────────────────┐
            │              EidosCore                   │
            │  (orquestador: pensar → decidir → R)     │
            └─────────────────────────────────────────┘
                  │                       │
                  ▼                       ▼
        ┌──────────────────┐    ┌──────────────────┐
        │ MonologueGenerator│    │  ActionRouter    │
        │  (JSON forzado)   │    │  (route_type)    │
        └──────────────────┘    └──────────────────┘
                  │                       │
                  ▼                       ▼
        ┌──────────────────┐    ┌──────────────────┐
        │  Stub Backend    │    │  Route decision  │
        │  (determinista)  │    │  ( RESPOND |     │
        │                  │    │    SEARCH_MEM |  │
        │  ← Fase 2:       │    │    CLARIFY |     │
        │     Qwen2.5-3B   │    │    CORTEX |      │
        │     via          │    │    MESH |        │
        │     llama-cpp)   │    │    SAFETY_BLOCK) │
        └──────────────────┘    └──────────────────┘
                  │
                  ▼
        ┌──────────────────┐
        │ data/monologues/ │
        │  <uuid>.json     │  ← traza metacognitiva (Fase 1.3)
        └──────────────────┘
```

### El monólogo interno — esquema

Cada pensamiento de EIDOS es **rígido** (JSON schema forzado) para compensar
la debilidad de modelos pequeños —enfoque neuro-simbólico:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-07-26T12:34:56Z",
  "input_summary": "¿Qué es EIDOS?",
  "observation": "Input recibido (14 chars, intent='question')...",
  "hypothesis": "El usuario probablemente busca question sobre 'eidos'...",
  "plan": [
    "Recuperar contexto previo sobre 'eidos' en memoria episódica.",
    "Formular respuesta concisa sobre 'eidos'.",
    "Verificar consistencia con capa semántica.",
    "Persistir interacción en memoria episódica."
  ],
  "risk": "none",
  "confidence": 0.65,
  "backend": "stub"
}
```

Cada monólogo se persiste en `data/monologues/<uuid>.json` para que la capa
metacognitiva (Fase 1.3) pueda responder *"¿por qué decidí X hace 3 días?"*.

---

## 🧩 Memoria cognitiva de 5 capas (Fase 1.2)

| # | Capa | Nombre | Backend | Propósito |
|---|------|--------|---------|-----------|
| 1 | Sensorial | Working memory | `deque` + SQLite | Contexto inmediato (últimos 50 eventos) |
| 2 | Episódica | Hipocampo | sqlite-vec + SQLite | "Qué pasó y cuándo" — vectorial |
| 3 | Semántica | Corteza | networkx → JSON | Grafo de conocimiento |
| 4 | Procedimental | Cerebelo | SQLite + `.eidos` files | Cápsulas y herramientas |
| 5 | Metacognitiva | Lóbulo Frontal | SQLite | Índice de monólogos pasados |

**Persistencia unificada** en un único `data/eidos.db` (máxima portabilidad pendrive) + `data/graph.json` + `data/capsules/*.eidos`.

**Embeddings stub**: en Fase 1.2 se usa un embedding determinista (bag-of-words + hash normalizado L2). Permite probar la capa vectorial sin GPU. En Fase 2 se sustituye por embeddings reales del Cortex Hub.

**TTL de cápsulas**: las cápsulas no-favoritas expiran si no se usan en `ttl_days` (default 7). El consolidador (Fase 1.3) las poda automáticamente. Las marcadas `favorite=true` nunca expiran.

---

## 🎯 Motivación intrínseca + Consolidación (Fase 1.3)

### Reward signal

EIDOS tiene **3 drivers motivacionales** que generan rewards internos (rango `[-1, +1]`):

| Driver | Peso | Origen | Trigger |
|--------|------|--------|---------|
| `curiosity` | +0.3 | MonologueGenerator | `confidence > avg_recent + 0.1` |
| `capsule_reuse` | +0.4 | ProceduralMemory | Cápsula invocada exitosamente |
| `user_satisfaction` | +0.3 / **-0.5** | Heurística sobre input del usuario | Racha de 3 turnos neutros = +0.3; señal negativa ("no", "mal", "incorrecto") = -0.5 |

Cada reward se persiste en tabla `reward_events` para auditoría. El consolidador los usa para inferir `outcome` (positive/negative/neutral) en monólogos sin outcome explícito — **metacognición**: EIDOS aprende qué estrategias funcionaron.

### Consolidador background

Hilo daemon que ejecuta un loop cada `consolidation_interval_sec` (default 300s):

1. **Compactación sensory→episódica**: promueve `response` con `confidence >= 0.6`.
2. **Indexación de monólogos huérfanos**: recovery tras crash (JSONs en disco no indexados).
3. **Inferencia de outcomes**: revisa rewards posteriores a cada monólogo y etiqueta outcome.
4. **Poda de cápsulas por TTL**: llama `procedural.expire_due()`.
5. **LRU episódica**: verifica overflow de `max_events`.

Cada run se persiste en `consolidation_runs` con métricas por paso.

---

## 🧩 Cortex Hub — Sentidos Periféricos (Fase 2)

El CortexHub es el gestor de los "sentidos" de EIDOS: modelos LLM locales para generar monólogos reales (no stub), embeddings reales para la capa episódica, y fallback a APIs externas con privacidad garantizada.

### Arquitectura

```
                    ┌─────────────────────────────────────────┐
                    │              CortexHub                   │
                    │  facade + lock singleton-virtual-ready  │
                    └─────────────────────────────────────────┘
                          │                │              │
                          ▼                ▼              ▼
                ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                │ ModelManager │  │ LlamaBackend │  │ APIFallback  │
                │ (download,  │  │ (GBNF grammar│  │ (PrivacyFilter│
                │  verify)    │  │  JSON forzado│  │  + OpenAI API)│
                └──────────────┘  └──────────────┘  └──────────────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │  Embedder    │
                                │  (real or    │
                                │   stub)      │
                                └──────────────┘
```

### Componentes

| Componente | Función |
|-----------|---------|
| **ModelManager** | Descarga HTTP con resume, verificación SHA256, registro en SQLite |
| **LlamaCppBackend** | Backend de monólogo con `llama-cpp-python` + GBNF grammar estricto |
| **LlamaCppEmbedder** | Embeddings reales (reemplaza `stub_embed` en EpisodicMemory) |
| **APIFallbackBackend** | Fallback a APIs OpenAI-compatibles, con PrivacyFilter SIEMPRE aplicado |
| **PrivacyFilter** | Redacción regex de PII (email, tel, IP, DNI, tarjeta, IBAN, URL con creds) |
| **CortexHub** | Facade + lock file (singleton-virtual-ready para Fase 4 MESH) |

### Backend 'auto' (degradación graceful)

```python
EidosCore(monologue_backend="auto", cortex_hub=hub)
# 1. Intenta LlamaCppBackend si hay modelo READY
# 2. Si no hay modelo o falla → degrada a StubBackend
# 3. Logs claros en cada paso
```

### PrivacyFilter — privacidad por diseño

Cuando se habilita `api_fallback`, **SIEMPRE** se aplica PrivacyFilter al input antes de enviarlo a la API externa. Patrones soportados:

- Email, Teléfono (ES + internacional), IPv4, DNI español
- Tarjeta de crédito, IBAN español, URL con credenciales

```bash
$ uv run eidos cortex privacy-test "Email: juan@test.com, IP: 10.0.0.1"
Original:  Email: juan@test.com, IP: 10.0.0.1
Filtrado:  Email: [REDACTED_EMAIL_1], IP: [REDACTED_IPV4_1]
Redactions: 2
```

### Lock singleton-virtual-ready (prepara Fase 4)

`CortexHub.try_acquire_lock(role, ttl)` usa `fcntl.flock` local en Fase 2. En Fase 4 se sustituirá por `resource_token` MESH distribuido sin cambiar la API. Solo un proceso EIDOS puede tener el lock activo — evita que dos instancias carguen el modelo en VRAM a la vez.

---

## 📁 Estructura del repo

```
eidos/
├── pyproject.toml              # uv + Python config
├── config/
│   ├── eidos.yaml              # Config maestra (vibe-coding friendly)
│   └── schemas/
│       └── capsule.schema.json # Schema de cápsulas .eidos (Fase 3)
├── eidos/                      # Paquete Python
│   ├── core/
│   │   ├── engine.py           # EidosCore (con integración MemoryStore)
│   │   ├── monologue.py        # Monologue + MonologueGenerator
│   │   └── router.py           # ActionRouter + Route
│   ├── memory/
│   │   ├── base.py             # Interfaz MemoryLayer
│   │   ├── sensory.py          # Capa 1
│   │   ├── episodic.py         # Capa 2 (sqlite-vec + bruteforce fallback)
│   │   ├── semantic.py         # Capa 3 (networkx)
│   │   ├── procedural.py       # Capa 4 (cápsulas .eidos)
│   │   ├── metacognitive.py    # Capa 5 (índice monólogos)
│   │   └── store.py            # Fachada MemoryStore
│   ├── cortex/                 # (Fase 2)
│   ├── utils/
│   │   ├── logging.py          # structlog wrapper
│   │   └── persistence.py      # Migraciones SQL versionadas
│   └── cli.py                  # REPL con rich + comando `stats`
├── data/                       # Persistencia portable (¡NUNCA al git!)
│   ├── eidos.db                # SQLite principal (4 tablas + vec)
│   ├── graph.json              # Grafo semántico
│   ├── monologues/             # JSONs de cada monólogo
│   ├── capsules/               # Archivos .eidos
│   └── migrations/             # SQL versionado
│       └── 0001_initial.sql
├── tests/                      # 74 tests pytest
└── docs/
    ├── 01-architecture.md
    └── deployment-portable.md
```

---

## ⚙️ Configuración

Edita [`config/eidos.yaml`](config/eidos.yaml). Es la **única fuente de verdad**
del núcleo, documentada inline. Cambios aplican al reiniciar.

---

## 🔒 Seguridad

- **Cero dependencias externas pesadas** para el usuario final.
- **Persistencia local** — los datos cognitivos NUNCA salen del SSD/pendrive salvo fallback a API (configurable, off por defecto).
- **Tool Sandbox** (Fase 3) con AST parsing + whitelist de módulos + aislamiento por proceso.

---

## 🛣️ Hoja de ruta

Ver la tabla de estado arriba. **El desarrollo es fase por fase** —no se avanza
hasta validar la anterior con tests.

---

## 📜 Licencia

MIT — ver [LICENSE](LICENSE).

---

**EIDOS** — *Construyamos la verdadera mente artificial.*
