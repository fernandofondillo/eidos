"""CLI de EIDOS — Fase 1.1.

REPL mínimo para hablar con EIDOS y visualizar su monólogo interno en vivo.
Uso:
    uv run eidos                # arranca REPL interactivo
    uv run eidos --once "..."   # una sola consulta
    uv run eidos --config path  # config custom
"""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from eidos import __version__
from eidos.core.engine import EidosCore
from eidos.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)
console = Console()

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "eidos.yaml"


def load_config(config_path: Path | None = None) -> dict:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        # Config mínima por defecto si no se encuentra el archivo.
        return {
            "core": {
                "monologue_backend": "stub",
                "confidence_threshold": 0.6,
                "persist_monologues": False,
                "max_plan_steps": 5,
            },
            "logging": {"level": "INFO", "format": "console"},
        }
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_core(config: dict, project_root: Path) -> EidosCore:
    core_cfg = config.get("core", {})
    persist = core_cfg.get("persist_monologues", False)
    monologues_dir = (project_root / core_cfg.get("monologues_dir", "data/monologues")) if persist else None

    return EidosCore(
        monologue_backend=core_cfg.get("monologue_backend", "stub"),
        confidence_threshold=float(core_cfg.get("confidence_threshold", 0.6)),
        monologues_dir=monologues_dir,
        max_plan_steps=int(core_cfg.get("max_plan_steps", 5)),
    )


@click.group(invoke_without_command=True)
@click.option("--config", "config_path", type=click.Path(exists=False, path_type=Path), default=None, help="Ruta a eidos.yaml")
@click.option("--once", "single_input", type=str, default=None, help="Ejecuta una sola consulta y sale.")
@click.option("--version", is_flag=True, help="Muestra versión y sale.")
def main(config_path: Path | None, single_input: str | None, version: bool) -> None:
    """EIDOS — Entidad Cognitiva Autónoma, Profunda y Enjambre."""
    if version:
        console.print(f"EIDOS v{__version__}")
        return

    config = load_config(config_path)
    project_root = (config_path or DEFAULT_CONFIG_PATH).resolve().parent.parent

    configure_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        format=config.get("logging", {}).get("format", "console"),
    )

    core = build_core(config, project_root)

    console.print(
        Panel.fit(
            f"[bold cyan]EIDOS[/] v{__version__}\n"
            f"Backend: [yellow]{core._generator.backend_name}[/]\n"
            f"Escribe [bold]exit[/] o [bold]Ctrl-D[/] para salir.",
            title="🧠 Cognitive Core",
            border_style="cyan",
        )
    )

    if single_input is not None:
        _handle_turn(core, single_input)
        return

    # REPL
    while True:
        try:
            user_input = Prompt.ask("[bold green]you>[/]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]EIDOS signing off.[/]")
            break
        if user_input.strip().lower() in {"exit", "quit", ":q"}:
            break
        if not user_input.strip():
            continue
        _handle_turn(core, user_input)


def _handle_turn(core: EidosCore, user_input: str) -> None:
    try:
        response = core.think_and_respond(user_input)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        logger.error("eidos_turn_error", error=str(e))
        return

    # Respuesta principal
    console.print(Panel(response.text, title="[bold blue]eidos>[/]", border_style="blue"))

    # Traza del monólogo en formato JSON para inspección (DEBUG-level info)
    console.print(
        Panel(
            Syntax(
                f'{{"monologue_id": "{response.monologue_id}", "route": "{response.route_type}", "confidence": {response.confidence}}}',
                "json",
                theme="ansi_dark",
                word_wrap=True,
            ),
            title="[dim]trace[/]",
            border_style="dim",
        )
    )


if __name__ == "__main__":
    main()
