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
| **1.1** | Estructura + Core Engine + MonologueGenerator (stub) | ✅ **Esta release** |
| 1.2   | 5 capas de memoria (SQLite + sqlite-vec + grafo JSON) | ⏳ Próxima |
| 1.3   | Motivación intrínseca + consolidación background | ⏳ |
| 2     | Cortex Hub — modelos GGUF/ONNX locales | ⏳ |
| 3     | Génesis dinámica de cápsulas + Tool Sandbox | ⏳ |
| 4     | EIDOS MESH — enjambre y cooperación | ⏳ |
| 5     | UI Tauri v2 + empaquetado cross-platform | ⏳ |

---

## 🚀 Quickstart (Fase 1.1)

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
# REPL interactivo — visualiza el monólogo interno en vivo
uv run eidos

# Una sola consulta
uv run eidos --once "¿Qué es EIDOS?"

# Con config custom
uv run eidos --config /path/to/eidos.yaml

# Versión
uv run eidos --version
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
│   │   ├── engine.py           # EidosCore
│   │   ├── monologue.py        # Monologue + MonologueGenerator
│   │   └── router.py           # ActionRouter + Route
│   ├── memory/                 # (Fase 1.2)
│   ├── cortex/                 # (Fase 2)
│   ├── utils/
│   │   └── logging.py          # structlog wrapper
│   └── cli.py                  # REPL con rich
├── data/                       # Persistencia portable (¡NUNCA al git!)
├── tests/                      # pytest
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
