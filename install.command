#!/usr/bin/env bash
# ============================================================================
# EIDOS — Bootstrap Mágico para macOS
# ============================================================================
# Este script instala EIDOS de forma autocontenido en el SSD/Pendrive.
# No usa el Python del sistema: descarga python-build-standalone (Indygreg).
# Al terminar, genera config/eidos.yaml y crea el Launcher.
#
# Uso: doble clic sobre install.command (macOS lo abre con Terminal.app)
# ============================================================================

set -euo pipefail

# --- Colores para output amigable ---
BOLD='\033[1m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
NC='\033[0m'

# --- Detección de directorio raíz ---
# El script vive en la raíz del repo/SSD. $0 puede ser relativo.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EIDOS_ROOT="$SCRIPT_DIR"
ENV_DIR="$EIDOS_ROOT/.eidos_env"
PYTHON_DIR="$ENV_DIR/python"
UV_DIR="$ENV_DIR/uv"
CONFIG_DIR="$EIDOS_ROOT/config"
MODELS_DIR="$EIDOS_ROOT/models"

# --- Versión de Python a instalar (python-build-standalone de Indygreg) ---
# Actualizar periódicamente. URL canónica:
# https://github.com/indygreg/python-build-standalone/releases
PYTHON_VERSION="3.12.7"
PYTHON_RELEASE="20241002"
PYTHON_BUILD_TAG="${PYTHON_VERSION}+${PYTHON_RELEASE}"

echo ""
echo -e "${CYAN}${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║                                                              ╎${NC}"
echo -e "${CYAN}${BOLD}║         🧠  EIDOS — Instalación Mágica  🧠                  ╎${NC}"
echo -e "${CYAN}${BOLD}║                                                              ╎${NC}"
echo -e "${CYAN}${BOLD}║    Tu mente artificial, portable y privada.                  ╎${NC}"
echo -e "${CYAN}${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${DIM}Este asistente instalará EIDOS de forma autocontenido.${NC}"
echo -e "${DIM}No se modificará tu sistema: todo queda en esta carpeta.${NC}"
echo ""

# ============================================================================
# 1. Detección de entorno (SSD externo vs disco local)
# ============================================================================

echo -e "${BOLD}1. Detección de entorno${NC}"

# En macOS, /Volumes/* contiene volúmenes montados. Si $EIDOS_ROOT empieza
# con /Volumes/, estamos en un SSD/Pendrive. Si no, en disco local.
if [[ "$EIDOS_ROOT" == /Volumes/* ]]; then
    VOL_NAME="$(echo "$EIDOS_ROOT" | cut -d'/' -f3)"
    echo -e "  ${GREEN}✓${NC} Detectado volumen externo: ${BOLD}${VOL_NAME}${NC}"
    echo -e "  ${DIM}EIDOS vivirá en este SSD/Pendrive y será portable.${NC}"
    IS_PORTABLE=true
else
    echo -e "  ${YELLOW}⚠${NC}  Detectado disco local (no un SSD externo)."
    echo -e "  ${DIM}EIDOS se instalará aquí, pero no será portable a otro ordenador.${NC}"
    echo -e "  ${DIM}Para portabilidad total, copia esta carpeta a un SSD/Pendrive y vuelve a ejecutar install.command.${NC}"
    IS_PORTABLE=false
fi
echo ""

# ============================================================================
# 2. Verificación de conexión a internet
# ============================================================================

echo -e "${BOLD}2. Verificación de conexión${NC}"
if ! ping -c 1 -t 3 github.com >/dev/null 2>&1; then
    echo -e "  ${RED}✗${NC} No hay conexión a internet."
    echo -e "  ${DIM}EIDOS necesita internet solo para la instalación inicial y descargar el cerebro local.${NC}"
    echo -e "  ${DIM}Después, funciona 100% offline.${NC}"
    read -p "  ¿Continuar de todas formas? (s/N): " CONT
    [[ "$CONT" =~ ^[sS]$ ]] || exit 1
else
    echo -e "  ${GREEN}✓${NC} Conexión a internet OK"
fi
echo ""

# ============================================================================
# 3. Detección de arquitectura (Apple Silicon vs Intel)
# ============================================================================

echo -e "${BOLD}3. Detección de arquitectura${NC}"
ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
    PYARCH="aarch64-apple-darwin"
    echo -e "  ${GREEN}✓${NC} Apple Silicon (M1/M2/M3/M4) detectado"
elif [[ "$ARCH" == "x86_64" ]]; then
    PYARCH="x86_64-apple-darwin"
    echo -e "  ${GREEN}✓${NC} Intel x86_64 detectado"
else
    echo -e "  ${RED}✗${NC} Arquitectura no soportada: $ARCH"
    exit 1
fi
echo ""

# ============================================================================
# 3.5 Red de Seguridad — Xcode Command Line Tools (CLT)
# ============================================================================
# Apple exige las CLT para compilar librerías nativas (como llama-cpp-python
# con Metal). Si no están instaladas, las instalamos de forma nativa vía
# xcode-select --install, pausamos para que el usuario interactúe con la
# ventana oficial de Apple, y re-verificamos. Si el usuario cancela, EIDOS
# simplemente funcionará en modo CPU (sin Metal) — nunca aborta.

echo -e "${BOLD}3.5 Herramientas de Apple (Red de Seguridad)${NC}"

# Detección silenciosa: xcode-select -p devuelve 0 si CLT está instalado.
XCODE_CLT_INSTALLED=false
if xcode-select -p > /dev/null 2>&1; then
    XCODE_CLT_INSTALLED=true
    echo -e "  ${GREEN}✓${NC} Xcode Command Line Tools ya instaladas"
else
    echo -e "  ${DIM}Las Herramientas de línea de comandos de Apple no están presentes.${NC}"
    echo -e "  ${DIM}Solicitando instalación oficial...${NC}"

    # Activación nativa: abre la ventana oficial de macOS.
    xcode-select --install > /dev/null 2>&1 || true

    # Pausa y guía humana: el script se detiene hasta que el usuario pulse ENTER.
    echo ""
    echo -e "  ${YELLOW}${BOLD}⚠️  EIDOS necesita una herramienta oficial de Apple para funcionar a máxima velocidad.${NC}"
    echo -e "  ${YELLOW}Se acaba de abrir una ventana en tu pantalla.${NC}"
    echo -e "  ${YELLOW}👉 Por favor, haz clic en 'Instalar' en esa ventana y acepta los términos.${NC}"
    echo -e "  ${YELLOW}⏳  Cuando termine la descarga e instalación, vuelve a esta ventana y pulsa la tecla ENTER para continuar.${NC}"
    echo ""
    read -p "  Pulsa ENTER cuando la instalación de Apple haya terminado..." _dummy

    # Re-verificación tras el ENTER del usuario.
    if xcode-select -p > /dev/null 2>&1; then
        XCODE_CLT_INSTALLED=true
        echo -e "  ${GREEN}✓${NC} Xcode Command Line Tools instaladas correctamente"
    else
        echo -e "  ${YELLOW}⚠${NC}  Parece que las herramientas no se terminaron de instalar."
        echo -e "  ${DIM}No te preocupes: EIDOS se instalará en modo compatible (CPU).${NC}"
        echo -e "  ${DIM}Podrás activar Metal más tarde desde el Panel de Configuración de la App.${NC}"
        XCODE_CLT_INSTALLED=false
    fi
fi
echo ""

# ============================================================================
# 4. Descarga e instalación de Python portable (python-build-standalone)
# ============================================================================

echo -e "${BOLD}4. Instalación de Python portable${NC}"
echo -e "  ${DIM}Descargando python-build-standalone v${PYTHON_BUILD_TAG}...${NC}"

mkdir -p "$ENV_DIR"
mkdir -p "$PYTHON_DIR"

PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PYTHON_RELEASE}/cpython-${PYTHON_BUILD_TAG}-${PYARCH}-install_only.tar.gz"
PYTHON_TARBALL="$ENV_DIR/python.tar.gz"

# Si ya está instalado, skip
if [[ -x "$PYTHON_DIR/bin/python3" ]]; then
    EXISTING_VER="$("$PYTHON_DIR/bin/python3" --version 2>&1 | awk '{print $2}')"
    echo -e "  ${GREEN}✓${NC} Python ${EXISTING_VER} ya instalado en .eidos_env/python/"
else
    # Descargar con curl, mostrar progreso
    if ! curl -L --fail --progress-bar "$PYTHON_URL" -o "$PYTHON_TARBALL"; then
        echo -e "  ${RED}✗${NC} Error descargando Python desde github.com/indygreg/python-build-standalone"
        echo -e "  ${DIM}Verifica tu conexión o prueba más tarde.${NC}"
        rm -f "$PYTHON_TARBALL"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Descarga completa. Extrayendo..."
    # El tarball contiene un dir "python/" — extraer directamente a ENV_DIR
    tar -xzf "$PYTHON_TARBALL" -C "$ENV_DIR"
    rm -f "$PYTHON_TARBALL"
    # El dir extraído se llama "python" — ya está en $PYTHON_DIR
    if [[ ! -x "$PYTHON_DIR/bin/python3" ]]; then
        echo -e "  ${RED}✗${NC} La extracción no produjo un binario Python válido."
        exit 1
    fi
    EXISTING_VER="$("$PYTHON_DIR/bin/python3" --version 2>&1 | awk '{print $2}')"
    echo -e "  ${GREEN}✓${NC} Python ${EXISTING_VER} instalado en .eidos_env/python/"
fi
echo ""

# ============================================================================
# 5. Instalación de uv (gestor de dependencias, también portable)
# ============================================================================

echo -e "${BOLD}5. Instalación de uv (gestor de paquetes)${NC}"
mkdir -p "$UV_DIR"
UV_BIN="$UV_DIR/uv"
if [[ -x "$UV_BIN" ]]; then
    echo -e "  ${GREEN}✓${NC} uv ya instalado en .eidos_env/uv/"
else
    echo -e "  ${DIM}Descargando uv...${NC}"
    # uv tiene un instalador oficial que respeta UV_INSTALL_DIR
    if ! curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$UV_DIR" sh >/dev/null 2>&1; then
        echo -e "  ${RED}✗${NC} Error instalando uv."
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} uv instalado en .eidos_env/uv/"
fi
echo ""

# ============================================================================
# 6. Configuración del entorno virtual (VENV dentro del SSD)
# ============================================================================

echo -e "${BOLD}6. Creación del entorno virtual${NC}"
export UV_PYTHON="$PYTHON_DIR/bin/python3"
VENV_DIR="$ENV_DIR/venv"

if [[ -x "$VENV_DIR/bin/python" ]]; then
    echo -e "  ${GREEN}✓${NC} Entorno virtual ya existe en .eidos_env/venv/"
else
    echo -e "  ${DIM}Creando entorno virtual con uv...${NC}"
    "$UV_BIN" venv "$VENV_DIR" --python "$PYTHON_DIR/bin/python3" >/dev/null 2>&1 || {
        echo -e "  ${RED}✗${NC} Error creando entorno virtual."
        exit 1
    }
    echo -e "  ${GREEN}✓${NC} Entorno virtual creado en .eidos_env/venv/"
fi
echo ""

# ============================================================================
# 7. Instalación de dependencias de EIDOS
# ============================================================================

echo -e "${BOLD}7. Instalación de dependencias de EIDOS${NC}"
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$UV_DIR:$VENV_DIR/bin:$PYTHON_DIR/bin:$PATH"

echo -e "  ${DIM}Sincronizando dependencias (puede tardar 1-2 minutos)...${NC}"
cd "$EIDOS_ROOT"
if ! "$UV_BIN" sync --active --no-dev >/dev/null 2>&1; then
    echo -e "  ${YELLOW}⚠${NC}  Algunas dependencias opcionales no se instalaron (es normal)."
    echo -e "  ${DIM}EIDOS funcionará en modo básico. Puedes instalar extras más tarde.${NC}"
else
    echo -e "  ${GREEN}✓${NC} Dependencias instaladas"
fi

# VERIFICACIÓN CRÍTICA: confirmar que structlog está en el venv correcto.
# Si no lo está, el launcher fallará silenciosamente.
if ! "$VENV_DIR/bin/python" -c "import structlog" >/dev/null 2>&1; then
    echo -e "  ${YELLOW}⚠${NC}  Las dependencias no se instalaron en el venv correcto. Corrigiendo..."
    "$UV_BIN" sync --active --no-dev >/dev/null 2>&1 || true
    if ! "$VENV_DIR/bin/python" -c "import structlog" >/dev/null 2>&1; then
        echo -e "  ${RED}✗${NC} Error crítico: las dependencias no se pudieron instalar."
        echo -e "  ${DIM}Ejecuta manualmente: VIRTUAL_ENV=$VENV_DIR $UV_BIN sync --active --extra cortex${NC}"
    else
        echo -e "  ${GREEN}✓${NC} Dependencias verificadas en venv portable"
    fi
else
    echo -e "  ${GREEN}✓${NC} Dependencias verificadas en venv portable"
fi
echo ""

# ============================================================================
# 8. Pregunta: ¿Descargar Cerebro Local (Qwen 2.5 3B)?
# ============================================================================

echo -e "${BOLD}8. Cerebro Local (Qwen 2.5 3B)${NC}"
echo -e "  ${DIM}EIDOS puede funcionar con un modelo de IA local para privacidad total.${NC}"
echo -e "  ${DIM}Esto ocupa ~2 GB y permite que EIDOS piense sin internet.${NC}"
echo -e "  ${DIM}Sin cerebro local, EIDOS usará un modo stub (limitado) o APIs externas.${NC}"
echo ""
read -p "  ¿Deseas que descargue tu Cerebro Local ahora? (Recomendado para privacidad total) [s/N]: " DOWNLOAD_BRAIN
DOWNLOAD_BRAIN="${DOWNLOAD_BRAIN:-N}"
if [[ "$DOWNLOAD_BRAIN" =~ ^[sS]$ ]]; then
    echo -e "  ${GREEN}✓${NC} Se descargará el cerebro local al final de la instalación."
    WANT_CORTEX=true
else
    echo -e "  ${DIM}No se descargará el cerebro local. Podrás hacerlo después desde la UI.${NC}"
    WANT_CORTEX=false
fi
echo ""

# ============================================================================
# 9. Pregunta: ¿Compilar llama-cpp-python con Metal (GPU)?
# ============================================================================
# Red de Seguridad: solo ofrecemos Metal si las CLT de Apple están instaladas
# (sección 3.5). Si el usuario las canceló o fallaron, saltamos directamente
# al modo CPU sin preguntar, para no generar expectativas que no se cumplirán.

COMPILE_METAL=false
if [[ "$WANT_CORTEX" == true && "$ARCH" == "arm64" ]]; then
    if [[ "$XCODE_CLT_INSTALLED" == true ]]; then
        echo -e "${BOLD}9. Aceleración por GPU (Metal)${NC}"
        echo -e "  ${DIM}En Apple Silicon, EIDOS puede usar la GPU para pensar 5-10x más rápido.${NC}"
        echo -e "  ${DIM}Esto requiere compilar una librería (~3 minutos).${NC}"
        read -p "  ¿Compilar con aceleración Metal? (Recomendado en M1/M2/M3/M4) [s/N]: " COMPILE
        COMPILE="${COMPILE:-N}"
        if [[ "$COMPILE" =~ ^[sS]$ ]]; then
            COMPILE_METAL=true
            echo -e "  ${GREEN}✓${NC} Se compilará con Metal."
        else
            echo -e "  ${DIM}No se compilará con Metal. EIDOS usará CPU (más lento).${NC}"
        fi
        echo ""
    else
        echo -e "${BOLD}9. Aceleración por GPU (Metal) — omitida${NC}"
        echo -e "  ${YELLOW}⚠${NC}  Las Herramientas de Apple no están instaladas, así que no podemos compilar con Metal."
        echo -e "  ${DIM}EIDOS funcionará en modo compatible (CPU). Podrás activar Metal más tarde.${NC}"
        echo ""
    fi
fi

# ============================================================================
# 10. Pregunta: ¿Activar MESH (enjambre)?
# ============================================================================

echo -e "${BOLD}$([ "$WANT_CORTEX" == true ] && echo '10' || echo '9'). Enjambre MESH${NC}"
echo -e "  ${DIM}EIDOS puede correr varias instancias en paralelo que cooperan.${NC}"
echo -e "  ${DIM}Útil si quieres que 3 EIDOS trabajen en tareas distintas a la vez.${NC}"
read -p "  ¿Activar MESH por defecto? [s/N]: " ACTIVATE_MESH
ACTIVATE_MESH="${ACTIVATE_MESH:-N}"
if [[ "$ACTIVATE_MESH" =~ ^[sS]$ ]]; then
    MESH_ENABLED=true
    echo -e "  ${GREEN}✓${NC} MESH activado."
else
    MESH_ENABLED=false
    echo -e "  ${DIM}MESH desactivado. Puedes activarlo después.${NC}"
fi
echo ""

# ============================================================================
# 11. Generación de config/eidos.yaml
# ============================================================================

echo -e "${BOLD}Generando config/eidos.yaml...${NC}"
mkdir -p "$CONFIG_DIR"

# Backend por defecto: si quiere cortex → 'auto', si no → 'stub'
if [[ "$WANT_CORTEX" == true ]]; then
    BACKEND="auto"
    CORTEX_ENABLED=true
else
    BACKEND="stub"
    CORTEX_ENABLED=false
fi

cat > "$CONFIG_DIR/eidos.yaml" << EOF
# EIDOS configuration — generado automáticamente por install.command
# Puedes editar este archivo manualmente, o usar la UI Web (botón ⚙ Settings).

meta:
  name: "EIDOS"
  version: "0.1.0"
  locale: "es-ES"
  identity: "Soy EIDOS, una entidad cognitiva autónoma, profunda y cooperativa."

core:
  monologue_backend: "${BACKEND}"
  confidence_threshold: 0.6
  persist_monologues: true
  monologues_dir: "data/monologues"
  max_plan_steps: 5

memory:
  sensory:
    window_size: 50
  episodic:
    backend: "sqlite_vec"
    db_path: "data/eidos.db"
    embedding_dim: 384
    max_events: 10000
  semantic:
    graph_path: "data/graph.json"
    backend: "networkx"
  procedural:
    capsules_dir: "data/capsules"
    default_ttl_days: 7
    favorite_preserve: true
  metacognitive:
    index_table: "monologue_index"
    consolidation_interval_sec: 300

cortex:
  enabled: ${CORTEX_ENABLED}
  models_dir: "models"
  default_model: "qwen2.5-3b-instruct-q4_k_m.gguf"
  vram_budget_mb: 4096
  fallback_to_api: true

mesh:
  enabled: ${MESH_ENABLED}
  transport: "unix_socket"
  runtime_dir: "data/runtime"
  lockfile_path: "/tmp/eidos.mesh.leader"
  heartbeat_sec: 2
  leader_timeout_sec: 6
  resource_token_ttl_sec: 30

evolution:
  enabled: true
  auto_forge: true
  sandbox_timeout_sec: 5
  sandbox_mem_mb: 256

logging:
  level: "INFO"
  format: "json"
  log_file: "data/eidos.log"
  rotate_max_mb: 10
  rotate_backups: 3
EOF
echo -e "  ${GREEN}✓${NC} config/eidos.yaml generado"
echo ""

# ============================================================================
# 12. Creación de directorios de datos
# ============================================================================

echo -e "${BOLD}Creando estructura de datos...${NC}"
mkdir -p "$EIDOS_ROOT/data/monologues"
mkdir -p "$EIDOS_ROOT/data/capsules"
mkdir -p "$EIDOS_ROOT/data/runtime"
mkdir -p "$EIDOS_ROOT/data/migrations"
mkdir -p "$MODELS_DIR"
# .gitkeep para que git trackee el dir
[[ ! -f "$EIDOS_ROOT/data/.gitkeep" ]] && touch "$EIDOS_ROOT/data/.gitkeep"
echo -e "  ${GREEN}✓${NC} Directorios listos"
echo ""

# ============================================================================
# 13. Descarga del cerebro local (si el usuario lo pidió)
# ============================================================================

if [[ "$WANT_CORTEX" == true ]]; then
    echo -e "${BOLD}Descargando Cerebro Local (Qwen 2.5 3B)...${NC}"

    if [[ "$COMPILE_METAL" == true ]]; then
        echo -e "  ${DIM}Compilando llama-cpp-python con Metal (esto tarda ~3 min)...${NC}"
        # Fallback Elegante (Anti-Fallo): envolvemos en if ! ... then.
        # Si la compilación con Metal falla por cualquier razón (C++, permisos,
        # versiones, etc.), el script NO ABORTA. Caemos a modo CPU y seguimos.
        if ! CMAKE_ARGS="-DGGML_METAL=on" "$UV_BIN" sync --active --extra cortex >/dev/null 2>&1; then
            echo -e "  ${YELLOW}⚙️  Activando modo de compatibilidad (CPU).${NC}"
            echo -e "  ${YELLOW}No te preocupes, EIDOS funcionará perfectamente y guardará toda tu memoria.${NC}"
            echo -e "  ${YELLOW}Podrás intentar activar la aceleración Metal más tarde desde el Panel de Configuración de la App.${NC}"
            echo ""
            echo -e "  ${DIM}Instalando cortex en modo CPU...${NC}"
            # Sin CMAKE_ARGS: instalación pura CPU, sin abortar si también falla.
            "$UV_BIN" sync --active --extra cortex >/dev/null 2>&1 || true
        else
            echo -e "  ${GREEN}✓${NC} llama-cpp-python compilado con Metal (GPU activa)"
        fi
    else
        # El usuario no pidió Metal (o no tenía CLT): instalar cortex en modo CPU.
        echo -e "  ${DIM}Instalando dependencias del cerebro local (modo CPU)...${NC}"
        "$UV_BIN" sync --active --extra cortex >/dev/null 2>&1 || true
    fi

    # Descargar el modelo GGUF usando el CLI de EIDOS
    # Registramos el modelo y lo descargamos
    "$VENV_DIR/bin/python" -c "
import sys
sys.path.insert(0, '$EIDOS_ROOT')
from eidos.cortex.manager import ModelManager
from pathlib import Path
mm = ModelManager(db_path=Path('$EIDOS_ROOT/data/eidos.db'), models_dir=Path('$MODELS_DIR'))
mm.register(
    model_id='qwen2.5-3b-instruct',
    name='Qwen2.5-3B-Instruct',
    filename='qwen2.5-3b-instruct-q4_k_m.gguf',
    url='https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf',
    format='gguf',
    purpose='monologue',
    quantization='Q4_K_M',
)
print('Descargando modelo (~2 GB)...')
path = mm.download('qwen2.5-3b-instruct')
print(f'Modelo descargado: {path}')
" || {
        echo -e "  ${YELLOW}⚠${NC}  No se pudo descargar el modelo ahora."
        echo -e "  ${DIM}Puedes hacerlo después desde la UI (botón 'Descargar Cerebro').${NC}"
    }
    echo ""
fi

# ============================================================================
# 14. Creación del Launcher (EIDOS.command)
# ============================================================================

echo -e "${BOLD}Creando Launcher (EIDOS.command)...${NC}"
cat > "$EIDOS_ROOT/EIDOS.command" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
# EIDOS Launcher — doble clic para despertar a EIDOS
# Ejecuta el servidor FastAPI en background y abre el navegador.

set -euo pipefail
EIDOS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$EIDOS_ROOT"

# Resolver Python portable
PYTHON_BIN="$EIDOS_ROOT/.eidos_env/venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
    # Fallback al sistema si no hay venv (desarrollo)
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi

# Verificar que EIDOS está instalado
if [[ ! -d "$EIDOS_ROOT/.eidos_env" ]]; then
    osascript -e 'display dialog "EIDOS no está instalado. Ejecuta install.command primero." with title "EIDOS" buttons {"OK"} default button 1 with icon stop'
    exit 1
fi

# VERIFICACIÓN CRÍTICA: comprobar que las dependencias están instaladas.
# Si no lo están, mostrar un error claro en vez de fallar silenciosamente.
if ! "$PYTHON_BIN" -c "import structlog, fastapi, pydantic" >/dev/null 2>&1; then
    echo "❌ Error: faltan dependencias de EIDOS."
    echo ""
    echo "Ejecuta este comando en Terminal para arreglarlo:"
    echo ""
    echo "  cd \"$EIDOS_ROOT\" && VIRTUAL_ENV=\"$EIDOS_ROOT/.eidos_env/venv\" \"$EIDOS_ROOT/.eidos_env/uv/uv\" sync --active --extra cortex"
    echo ""
    echo "O vuelve a ejecutar install.command."
    echo ""
    osascript -e "display dialog \"Faltan dependencias de EIDOS. Abre Terminal y ejecuta:

cd \\\"$EIDOS_ROOT\\\" && VIRTUAL_ENV=\\\"$EIDOS_ROOT/.eidos_env/venv\\\" \\\"$EIDOS_ROOT/.eidos_env/uv/uv\\\" sync --active --extra cortex

O vuelve a ejecutar install.command.\" with title \"EIDOS - Error\" buttons {\"OK\"} default button 1 with icon stop"
    read -p "Pulsa ENTER para cerrar..."
    exit 1
fi

# Matar instancias previas (si las hay)
pkill -f "eidos web" 2>/dev/null || true
sleep 0.5

# Iniciar servidor en background, redirigiendo output a log
LOG_FILE="$EIDOS_ROOT/data/eidos_server.log"
mkdir -p "$EIDOS_ROOT/data"
nohup "$PYTHON_BIN" -m eidos web --port 8765 --host 127.0.0.1 > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$EIDOS_ROOT/.eidos_env/server.pid"

# Esperar a que el servidor esté listo (máx 15 segundos)
echo "Iniciando EIDOS..."
READY=false
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 0.5
done

if [[ "$READY" != "true" ]]; then
    echo "❌ EIDOS no pudo arrancar. Revisa el log:"
    echo "  $LOG_FILE"
    echo ""
    echo "Últimas 10 líneas del log:"
    tail -10 "$LOG_FILE" 2>/dev/null || echo "(log vacío)"
    echo ""
    read -p "Pulsa ENTER para cerrar..."
    exit 1
fi

# Abrir navegador
open "http://127.0.0.1:8765"

# Esperar a que el usuario cierre (mantener proceso vivo)
# Cuando el usuario mate este proceso (cerrar Terminal o Cmd+Q), matamos el server
trap "kill $SERVER_PID 2>/dev/null; exit 0" SIGINT SIGTERM EXIT

# En macOS, podemos mostrar una notificación al usuario
osascript -e 'display notification "EIDOS está listo. Cierra esta ventana para detenerlo." with title "EIDOS" sound name "Glass"'

# Mantener vivo hasta SIGINT/SIGTERM
wait $SERVER_PID
LAUNCHER_EOF

chmod +x "$EIDOS_ROOT/EIDOS.command"
echo -e "  ${GREEN}✓${NC} EIDOS.command creado (doble-clic para despertar EIDOS)"

# En macOS, asignar icono al .command (usando .icns si existe)
if [[ -f "$EIDOS_ROOT/desktop/icons/icon.icns" ]]; then
    # Asignar icono al .command vía SetFile (si disponible)
    if command -v SetFile >/dev/null 2>&1; then
        SetFile -a C "$EIDOS_ROOT/EIDOS.command" 2>/dev/null || true
    fi
fi
echo ""

# ============================================================================
# 15. Limpieza y mensaje final
# ============================================================================

# Crear .env vacío para API keys (la UI lo llenará)
[[ ! -f "$EIDOS_ROOT/.env" ]] && cat > "$EIDOS_ROOT/.env" << 'ENV_EOF'
# API Keys — gestionado por la UI Web (botón ⚙ Settings)
# No edites este archivo manualmente.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
MINIMAX_API_KEY=
ENV_EOF

# README visible en el SSD
cat > "$EIDOS_ROOT/LEEME.txt" << 'README_EOF'
═══════════════════════════════════════════════════════════════
                    🧠  EIDOS  🧠
        Tu mente artificial, portable y privada
═══════════════════════════════════════════════════════════════

PARA EMPEZAR:
  1. Doble clic sobre  EIDOS.command
  2. Se abrirá tu navegador con la interfaz de EIDOS.
  3. ¡Habla con EIDOS!

PARA LLEVARTE A EIDOS A OTRO ORDENADOR:
  Copia toda esta carpeta a otro SSD/Pendrive y haz doble clic
  en EIDOS.command. Tu memoria cognitiva viaja contigo.

AYUDA:
  - Manual completo: docs/USER_MANUAL.md
  - Resolver problemas: docs/USER_MANUAL.md#resolución-de-problemas

═══════════════════════════════════════════════════════════════
README_EOF

echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║                                                              ╎${NC}"
echo -e "${GREEN}${BOLD}║              🎉  ¡EIDOS está listo!  🎉                       ╎${NC}"
echo -e "${GREEN}${BOLD}║                                                              ╎${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Para empezar:${NC}"
echo -e "  ${GREEN}→${NC} Haz doble clic en ${BOLD}EIDOS.command${NC} en esta carpeta."
echo -e "  ${DIM}Se abrirá tu navegador con la interfaz de EIDOS.${NC}"
echo ""
echo -e "${BOLD}Para llevarte EIDOS a otro ordenador:${NC}"
echo -e "  ${DIM}Copia toda esta carpeta a otro SSD/Pendrive y haz doble clic en EIDOS.command.${NC}"
echo ""
echo -e "${BOLD}Manual completo:${NC}"
echo -e "  ${DIM}docs/USER_MANUAL.md${NC}"
echo ""
echo -e "${BOLD}Para actualizar EIDOS en el futuro:${NC}"
echo -e "  ${DIM}Vuelve a ejecutar install.command. Tu memoria (data/) se preserva.${NC}"
echo ""
read -p "Pulsa ENTER para cerrar esta ventana..."
