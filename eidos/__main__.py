"""EIDOS — Punto de entrada para `python -m eidos`.

Permite ejecutar EIDOS desde la línea de comandos:
    python -m eidos web          → arranca el servidor web
    python -m eidos --version    → muestra la versión
"""

from __future__ import annotations

import sys


def main() -> None:
    """Entry point para `python -m eidos`."""
    if len(sys.argv) < 2:
        print("Uso: python -m eidos <comando>")
        print("Comandos disponibles:")
        print("  web       Arranca el servidor web (FastAPI + frontend)")
        print("  --version Muestra la versión")
        sys.exit(1)

    command = sys.argv[1]

    if command == "--version" or command == "-v":
        from eidos import __version__
        print(f"EIDOS v{__version__}")
        sys.exit(0)

    if command == "web":
        # Poner los argumentos restantes para que run() los procese
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from eidos.web.server import run
        run()
        return

    print(f"Comando desconocido: {command}")
    print("Comandos disponibles: web, --version")
    sys.exit(1)


if __name__ == "__main__":
    main()
