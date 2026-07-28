#!/usr/bin/env bash
# ============================================================================
# EIDOS — Instalador desde GitHub para macOS
# ============================================================================
# Este script descarga EIDOS directamente desde GitHub al SSD del usuario.
# No necesitas descargar ningún ZIP ni tener archivos previos.
#
# Uso:
#   1. Conecta tu SSD a tu Mac.
#   2. Abre Terminal (Cmd + Espacio → Terminal).
#   3. Ejecuta: bash -c "$(curl -fsSL https://raw.githubusercontent.com/fernandofondillo/eidos/main/install_from_github.command)"
#
# O si prefieres descargar este script primero:
#   1. curl -fsSL https://raw.githubusercontent.com/fernandofondillo/eidos/main/install_from_github.command -o /tmp/eidos_install.command
#   2. bash /tmp/eidos_install.command
# ============================================================================

set -euo pipefail

# --- Colores ---
BOLD='\033[1m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
NC='\033[0m'

REPO_URL="https://github.com/fernandofondillo/eidos.git"
REPO_BRANCH="main"

echo ""
echo -e "${CYAN}${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║                                                              ╎${NC}"
echo -e "${CYAN}${BOLD}║    🧠  EIDOS — Instalación desde GitHub  🧠                  ╎${NC}"
echo -e "${CYAN}${BOLD}║                                                              ╎${NC}"
echo -e "${CYAN}${BOLD}║    Tu mente artificial, portable y privada.                  ╎${NC}"
echo -e "${CYAN}${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${DIM}Este script descargará EIDOS desde GitHub y lo instalará en tu SSD.${NC}"
echo -e "${DIM}No necesitas descargar ningún ZIP ni tener archivos previos.${NC}"
echo ""

# ============================================================================
# 1. Seleccionar dónde instalar (SSD o disco local)
# ============================================================================

echo -e "${BOLD}1. ¿Dónde quieres instalar EIDOS?${NC}"
echo ""
echo -e "  ${BOLD}Volúmenes disponibles:${NC}"

# Listar volúmenes montados
volumes=()
if [[ -d /Volumes ]]; then
    while IFS= read -r vol; do
        [[ -z "$vol" ]] && continue
        volumes+=("$vol")
    done < <(ls /Volumes/ 2>/dev/null)
fi

# Añadir opción de disco local (home)
volumes+=("$HOME/Desktop/eidos")
volumes+=("$HOME/eidos")

i=1
for vol in "${volumes[@]}"; do
    if [[ "$vol" == "$HOME"* ]]; then
        echo -e "  ${BOLD}$i${NC}. Disco local: ~/${vol#$HOME/}"
    else
        echo -e "  ${BOLD}$i${NC}. SSD externo: /Volumes/$vol"
    fi
    ((i++))
done

echo ""
echo -e "  ${BOLD}0${NC}. Escribir ruta manualmente"
echo ""
read -p "Selecciona un número (1-$((${#volumes[@]}))): " choice

if [[ "$choice" == "0" ]]; then
    read -p "Escribe la ruta completa donde instalar EIDOS: " INSTALL_PARENT
elif [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#volumes[@]} )); then
    selected="${volumes[$((choice-1))]}"
    if [[ "$selected" == "$HOME"* ]]; then
        INSTALL_PARENT="$selected"
    else
        INSTALL_PARENT="/Volumes/$selected"
    fi
else
    echo -e "  ${RED}✗${NC} Opción no válida."
    exit 1
fi

# Construir ruta final: INSTALL_PARENT/eidos
INSTALL_DIR="$INSTALL_PARENT/eidos"

echo ""
echo -e "  ${GREEN}✓${NC} EIDOS se instalará en: ${BOLD}$INSTALL_DIR${NC}"

# Detectar si es SSD externo
if [[ "$INSTALL_PARENT" == /Volumes/* ]]; then
    VOL_NAME="$(echo "$INSTALL_PARENT" | cut -d'/' -f3)"
    echo -e "  ${DIM}Volumen externo detectado: $VOL_NAME — EIDOS será portable.${NC}"
else
    echo -e "  ${YELLOW}⚠${NC}  Disco local detectado. EIDOS no será portable a otro ordenador."
fi
echo ""

# ============================================================================
# 2. Verificar que git está disponible
# ============================================================================

echo -e "${BOLD}2. Verificando herramientas del sistema...${NC}"

if ! command -v git >/dev/null 2>&1; then
    echo -e "  ${YELLOW}⚠${NC}  Git no está instalado."
    echo -e "  ${DIM}Instalando Command Line Tools de Apple (incluye git)...${NC}"
    xcode-select --install >/dev/null 2>&1 || true
    echo ""
    echo -e "  ${YELLOW}⚠️  Se ha abierto una ventana para instalar las herramientas de Apple.${NC}"
    echo -e "  ${YELLOW}👉 Pulsa 'Instalar', acepta los términos, y cuando termine vuelve aquí y pulsa ENTER.${NC}"
    read -p "  Pulsa ENTER cuando la instalación de Apple haya terminado..." _dummy

    if ! command -v git >/dev/null 2>&1; then
        echo -e "  ${RED}✗${NC} Git sigue sin estar disponible. Instálalo manualmente."
        exit 1
    fi
fi
echo -e "  ${GREEN}✓${NC} Git disponible"
echo ""

# ============================================================================
# 3. Clonar el repositorio desde GitHub
# ============================================================================

echo -e "${BOLD}3. Descargando EIDOS desde GitHub...${NC}"

# Crear directorio padre si no existe
mkdir -p "$INSTALL_PARENT"

# Si ya existe la carpeta eidos, preguntar
if [[ -d "$INSTALL_DIR" ]]; then
    echo -e "  ${YELLOW}⚠${NC}  Ya existe una carpeta 'eidos' en $INSTALL_PARENT"
    read -p "  ¿Quieres actualizarla? (se conservará tu memoria en data/) [s/N]: " update_existing
    update_existing="${update_existing:-N}"
    if [[ "$update_existing" =~ ^[sS]$ ]]; then
        cd "$INSTALL_DIR"
        echo -e "  ${DIM}Actualizando desde GitHub...${NC}"
        git pull origin "$REPO_BRANCH" >/dev/null 2>&1 || {
            echo -e "  ${YELLOW}⚠${NC}  No se pudo actualizar. Se reinstalará desde cero."
            cd "$INSTALL_PARENT"
            rm -rf "$INSTALL_DIR"
            git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -3
        }
    else
        echo -e "  ${DIM}Instalando en carpeta nueva 'eidos_new'...${NC}"
        INSTALL_DIR="$INSTALL_PARENT/eidos_new"
        git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -3
    fi
else
    cd "$INSTALL_PARENT"
    echo -e "  ${DIM}Clonando repositorio (puede tardar 30-60 segundos)...${NC}"
    git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR" 2>&1 | tail -3
fi

if [[ ! -f "$INSTALL_DIR/install.command" ]]; then
    echo -e "  ${RED}✗${NC} La descarga no se completó correctamente."
    exit 1
fi

echo -e "  ${GREEN}✓${NC} EIDOS descargado en: $INSTALL_DIR"
echo ""

# ============================================================================
# 4. Quitar cuarentena de macOS (Gatekeeper)
# ============================================================================

echo -e "${BOLD}4. Quitando cuarentena de macOS (Gatekeeper)...${NC}"
xattr -dr com.apple.quarantine "$INSTALL_DIR" 2>/dev/null || true
chmod +x "$INSTALL_DIR/install.command" 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Listo — macOS no bloqueará la instalación"
echo ""

# ============================================================================
# 5. Ejecutar el instalador de EIDOS
# ============================================================================

echo -e "${BOLD}5. Iniciando instalador de EIDOS...${NC}"
echo ""
echo -e "${DIM}Se ejecutará install.command ahora. Responde a las preguntas que aparezcan.${NC}"
echo -e "${DIM}Cuando termine, haz doble clic en EIDOS.command para despertar a EIDOS.${NC}"
echo ""
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cd "$INSTALL_DIR"
exec ./install.command
