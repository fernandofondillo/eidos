# Despliegue Portable de EIDOS

> **Principio**: EIDOS vive en un SSD/Pendrive. Cero dependencias externas para el usuario final.

## 1. Modelo de portabilidad

```
SSD/Pendrive
└── eidos/
    ├── app/                  # binarios + código (immutable)
    ├── data/                 # memoria cognitiva (privada, mutable)
    ├── models/               # LLMs GGUF/ONNX (Fase 2)
    └── config/eidos.yaml     # configuración
```

El usuario conecta el SSD a cualquier Mac/Windows/Linux, ejecuta `./eidos` o el .app/.exe, y su mente artificial está lista con toda su memoria.

## 2. Requisitos por plataforma

### macOS (Apple Silicon — entorno primario)

```bash
# Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clonar o copiar al SSD
cp -R eidos /Volumes/MI_SSD/eidos
cd /Volumes/MI_SSD/eidos

# Sincronizar
uv sync

# Ejecutar
uv run eidos
```

**Notas Apple Silicon**:
- Python 3.11+ nativo ARM64 vía uv (no hace falta pyenv).
- `llama-cpp-python` (Fase 2) se compila con Metal: `CMAKE_ARGS="-DGGML_METAL=on" uv sync --extra cortex`.
- El modelo Qwen2.5-3B Q4_K_M ocupa ~2GB — cabe holgado en VRAM unificada.

### Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /path/to/eidos
uv sync
uv run eidos
```

### Windows

```powershell
# PowerShell
irm https://astral.sh/uv/install.ps1 | iex
cd D:\eidos
uv sync
uv run eidos
```

## 3. Empaquetado final (Fase 5)

En Fase 5 se empaqueta con Tauri v2:

- **Backend Python**: compilado a binario standalone con `PyOxidizer` o `Nuitka`, distribuido como recurso dentro del bundle Tauri.
- **Frontend**: React/Svelte, visualiza monólogo, cápsulas y mapa del enjambre.
- **Plataformas**: macOS (.dmg, .app), Windows (.msi, .exe), Linux (.AppImage, .deb), iOS, Android.

Hasta entonces, el "empaquetado" es el repo + `uv sync`.

## 4. Backup y portabilidad de la memoria

La carpeta `data/` contiene toda la identidad cognitiva del EIDOS:

- `eidos.db` — SQLite principal (capas sensorial, episódica, procedimental, metacognitiva).
- `graph.json` — grafo semántico.
- `monologues/` — trazas de pensamiento (metacognición).
- `capsules/` — archivos `.eidos` (especializaciones).

**Para migrar EIDOS a otro dispositivo**: copia la carpeta `data/` intacta. Eso es todo.

**Backup recomendado**: cron job o launchd que comprima `data/` a un `.tar.zst` con timestamp.

## 5. Privacy by design

- Sin telemetría. Sin calls externas por defecto.
- `cortex.fallback_to_api: false` en config para garantizar 100% offline.
- Si se habilita API fallback (Fase 2.3), los datos sensibles se filtran antes del envío (módulo `cortex.privacy_filter`).

## 6. Multi-instancia en el mismo SSD (Fase 4)

```bash
# Terminal 1 — Primario
EIDOS_MESH_ROLE=leader uv run eidos

# Terminal 2 — Worker
EIDOS_MESH_ROLE=worker uv run eidos

# Terminal 3 — Worker
EIDOS_MESH_ROLE=worker uv run eidos
```

Los tres comparten `/data` (SQLite WAL), se descubren vía socket `/tmp/eidos.mesh.sock`, y el Primario arbitra el uso del Cortex Hub.
