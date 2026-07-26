#!/usr/bin/env bash
# EIDOS — desarrollo local (macOS Apple Silicon primario, cross-platform)
# Arranca el REPL con la config por defecto.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run eidos "$@"
