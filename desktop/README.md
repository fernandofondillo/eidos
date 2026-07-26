# EIDOS Desktop — Tauri v2

> Wrapper nativo para Mac/Windows/Linux. Empaqueta el frontend React + el backend Python en un único binario portable.

## Arquitectura

```
┌─────────────────────────────────────────┐
│           EIDOS.app (.dmg)              │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │  Tauri v2   │  │  Python sidecar  │  │
│  │  (Rust)     │──│  (FastAPI +      │  │
│  │  WebKit     │  │   EidosCore)     │  │
│  │  UI shell   │  │  localhost:8765  │  │
│  └─────────────┘  └──────────────────┘  │
│         ↕ IPC / HTTP                    │
│  ┌─────────────────────────────────────┐│
│  │  React UI (ui/dist/)                ││
│  │  - Chat + Monólogo                  ││
│  │  - Memoria 5 capas                  ││
│  │  - Cápsulas                         ││
│  │  - Mapa MESH                        ││
│  │  - Reward signal                    ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

## Requisitos

- **Rust** 1.70+ (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- **Tauri CLI v2** (`cargo install tauri-cli --version "^2.0"`)
- **Node.js** 18+ (para compilar el frontend)
- **Python 3.11+** (para el sidecar; ver abajo cómo empaquetarlo)

## Desarrollo

```bash
# Desde la raíz del proyecto
cd desktop
cargo tauri dev
```

Esto:
1. Compila el frontend (`cd ../ui && npm run build`)
2. Lanza Vite dev server en :5173
3. Compila Tauri y abre la ventana nativa
4. El frontend carga desde `http://localhost:5173` (HMR activo)

## Producción — empaquetar para distribución

### Paso 1: Empaquetar Python como binario standalone

Usa `PyOxidizer` o `Nuitka` para compilar el backend Python a un binario nativo:

```bash
# Opción A: PyOxidizer (recomendado)
pip install pyoxidizer
pyoxidizer build --release
# Output: build/<platform>/release/eidos-server

# Opción B: Nuitka
pip install nuitka
python -m nuitka --standalone --onefile \
    --include-package=eidos \
    --output-filename=eidos-server \
    eidos/web/server.py
```

Copia el binario resultante a `desktop/binaries/eidos-server` (o `eidos-server.exe` en Windows).

### Paso 2: Compilar Tauri para cada plataforma

```bash
# macOS Apple Silicon (.dmg + .app)
cd desktop
cargo tauri build --target aarch64-apple-darwin

# macOS Intel
cargo tauri build --target x86_64-apple-darwin

# Windows (.msi + .exe) — desde Windows o cross-compile
cargo tauri build --target x86_64-pc-windows-msvc

# Linux (.AppImage + .deb)
cargo tauri build --target x86_64-unknown-linux-gnu
```

Output: `desktop/target/release/bundle/<platform>/EIDOS.<ext>`

### Paso 3: Portable SSD/Pendrive

El bundle final debe tener esta estructura para ser 100% portable:

```
SSD/Pendrive
└── EIDOS/
    ├── EIDOS.app/            # o EIDOS.exe / EIDOS.AppImage
    ├── bin/
    │   └── eidos-server      # Python compilado standalone
    ├── config/
    │   └── eidos.yaml
    └── data/                 # memoria cognitiva del usuario
        ├── eidos.db
        ├── graph.json
        ├── monologues/
        ├── capsules/
        └── migrations/
```

El usuario conecta el SSD a cualquier Mac/Win/Linux, hace doble clic en EIDOS.app, y su mente artificial está lista con toda su memoria.

## iOS y Android (futuro)

Tauri v2 soporta móvil (en beta). La arquitectura sería la misma, pero el sidecar Python necesitaría recompilarse para ARM móvil. Alternativa: usar el backend Python en un servidor remoto y que la app móvil sea solo cliente.

## Troubleshooting

### "sidecar not found"
Asegúrate de que `desktop/binaries/eidos-server` existe y tiene permisos de ejecución (`chmod +x`).

### "WebView2 not installed" (Windows)
Tauri usa WebView2 en Windows. Descárgalo de https://developer.microsoft.com/microsoft-edge/webview2/

### "PyOxidizer build fails en macOS"
Asegúrate de tener Xcode Command Tools: `xcode-select --install`

### Modelos GGUF no cargan
El sidecar Python necesita `llama-cpp-python` compilado con Metal:
```bash
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python
```
