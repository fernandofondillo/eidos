"""CLI de EIDOS — Fase 1.3.

REPL con memoria cognitiva, motivación intrínseca y consolidación
en background. Visualiza monólogo interno, contexto recuperado y
reward signal del turno.

Uso:
    uv run eidos                       # REPL interactivo
    uv run eidos --once "..."          # una sola consulta
    uv run eidos stats                 # estadísticas de las 5 capas
    uv run eidos motivation            # métricas de reward signal
    uv run eidos consolidate           # ejecutar consolidación manual
    uv run eidos runs                  # historial de consolidation_runs
    uv run eidos --config path         # config custom
"""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from eidos import __version__
from eidos.core.consolidator import Consolidator
from eidos.core.engine import EidosCore
from eidos.core.motivation import MotivationModule
from eidos.memory.store import MemoryStore
from eidos.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)
console = Console()

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "eidos.yaml"


def load_config(config_path: Path | None = None) -> dict:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return {
            "core": {
                "monologue_backend": "stub",
                "confidence_threshold": 0.6,
                "persist_monologues": False,
                "max_plan_steps": 5,
            },
            "memory": {},
            "logging": {"level": "INFO", "format": "console"},
        }
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_core(config: dict, project_root: Path, start_consolidator: bool = True) -> EidosCore:
    core_cfg = config.get("core", {})
    persist = core_cfg.get("persist_monologues", False)
    monologues_dir = (project_root / core_cfg.get("monologues_dir", "data/monologues")) if persist else None
    if monologues_dir is not None:
        monologues_dir.mkdir(parents=True, exist_ok=True)

    # Fase 1.2: MemoryStore
    memory = MemoryStore.from_config(config, project_root)

    # Fase 1.3: MotivationModule + Consolidator
    db_path = memory.db_path
    motivation = MotivationModule(
        db_path=db_path,
        procedural=memory.procedural,
    )
    metacog_cfg = config.get("memory", {}).get("metacognitive", {})
    consolidator = Consolidator(
        memory=memory,
        db_path=db_path,
        monologues_dir=monologues_dir or (project_root / "data" / "monologues"),
        interval_sec=int(metacog_cfg.get("consolidation_interval_sec", 300)),
    )

    return EidosCore(
        monologue_backend=core_cfg.get("monologue_backend", "stub"),
        confidence_threshold=float(core_cfg.get("confidence_threshold", 0.6)),
        monologues_dir=monologues_dir,
        max_plan_steps=int(core_cfg.get("max_plan_steps", 5)),
        memory=memory,
        motivation=motivation,
        consolidator=consolidator,
        auto_start_consolidator=start_consolidator,
    )


@click.group(invoke_without_command=True)
@click.option("--config", "config_path", type=click.Path(exists=False, path_type=Path), default=None, help="Ruta a eidos.yaml")
@click.option("--once", "single_input", type=str, default=None, help="Ejecuta una sola consulta y sale.")
@click.option("--version", is_flag=True, help="Muestra versión y sale.")
@click.option("--no-consolidator", is_flag=True, help="No arrancar el consolidador background (útil para tests).")
@click.pass_context
def main(
    ctx: click.Context,
    config_path: Path | None,
    single_input: str | None,
    version: bool,
    no_consolidator: bool,
) -> None:
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

    # Subcomandos no necesitan el core completo
    if ctx.invoked_subcommand is not None:
        ctx.obj = {
            "config": config,
            "project_root": project_root,
            "start_consolidator": not no_consolidator,
        }
        return

    core = build_core(config, project_root, start_consolidator=not no_consolidator)

    console.print(
        Panel.fit(
            f"[bold cyan]EIDOS[/] v{__version__}\n"
            f"Backend: [yellow]{core._generator.backend_name}[/]\n"
            f"Memoria: [green]5 capas activas[/]\n"
            f"Motivación: [magenta]reward signal ON[/]\n"
            f"Consolidador: [{'green' if core._consolidator and core._consolidator.is_running() else 'red'}]"
            f"{'running' if core._consolidator and core._consolidator.is_running() else 'stopped'}[/]\n"
            f"Escribe [bold]exit[/] o [bold]Ctrl-D[/] para salir.",
            title="🧠 Cognitive Core",
            border_style="cyan",
        )
    )

    try:
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
    finally:
        core.shutdown()


@main.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Muestra estadísticas de las 5 capas de memoria."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)

    table = Table(title="🧠 EIDOS — Memory Stats", show_header=True, header_style="bold cyan")
    table.add_column("Capa", style="bold")
    table.add_column("Métricas", style="white")

    for layer in memory.all_layers():
        s = layer.stats()
        layer_name = s.pop("layer", layer.layer_name)
        metrics = "\n".join(f"{k}: [yellow]{v}[/]" for k, v in s.items())
        table.add_row(layer_name, metrics)

    console.print(table)


@main.command()
@click.pass_context
def motivation(ctx: click.Context) -> None:
    """Muestra estadísticas del reward signal (motivación intrínseca)."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)

    mm = MotivationModule(db_path=memory.db_path, procedural=memory.procedural)
    s = mm.stats()

    table = Table(title="🎯 EIDOS — Motivation Stats", show_header=True, header_style="bold magenta")
    table.add_column("Métrica", style="bold")
    table.add_column("Valor", style="white")
    table.add_row("Reward total (sesión)", f"[yellow]{s['session_total_reward']}[/]")
    table.add_row("Ventana confidence (size)", f"{s['confidence_window_size']}")
    table.add_row("Streak satisfacción (turnos)", f"{s['satisfaction_streak']} / {s['satisfaction_window']}")
    console.print(table)

    by_driver = s["by_driver"]
    if by_driver:
        dtable = Table(title="Rewards por driver", show_header=True, header_style="bold magenta")
        dtable.add_column("Driver", style="bold")
        dtable.add_column("Count", style="white")
        dtable.add_column("Σ delta", style="white")
        for driver, m in by_driver.items():
            dtable.add_row(driver, str(m["count"]), f"{m['total_delta']:+.4f}")
        console.print(dtable)
    else:
        console.print("[dim]Aún no hay rewards registrados.[/]")


@main.command()
@click.pass_context
def consolidate(ctx: click.Context) -> None:
    """Ejecuta una consolidación manual inmediata."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="INFO", format="console")
    memory = MemoryStore.from_config(config, project_root)
    monologues_dir = project_root / "data" / "monologues"

    cons = Consolidator(
        memory=memory,
        db_path=memory.db_path,
        monologues_dir=monologues_dir,
        interval_sec=300,
    )
    result = cons.run_once(kind="manual")
    console.print(
        Panel(
            f"Items procesados: [yellow]{result['items_processed']}[/]\n"
            f"Duración: [yellow]{result['duration_ms']} ms[/]\n\n"
            + "\n".join(f"  {k}: [cyan]{v}[/]" for k, v in result["details"].items()),
            title=f"✅ Consolidación manual @ {result['ts']}",
            border_style="green",
        )
    )


@main.command()
@click.pass_context
def runs(ctx: click.Context) -> None:
    """Historial de ejecuciones del consolidador."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)
    cons = Consolidator(
        memory=memory,
        db_path=memory.db_path,
        monologues_dir=project_root / "data" / "monologues",
    )
    recent = cons.recent_runs(limit=15)

    if not recent:
        console.print("[dim]Aún no hay ejecuciones del consolidador.[/]")
        return

    table = Table(title="🔄 Consolidation runs (últimas 15)", show_header=True, header_style="bold cyan")
    table.add_column("ts", style="dim")
    table.add_column("kind", style="bold")
    table.add_column("items", style="yellow")
    table.add_column("ms", style="white")
    table.add_column("details", style="white")
    for r in recent:
        details_str = ", ".join(f"{k}={v}" for k, v in r["details"].items()) if r["details"] else ""
        table.add_row(r["ts"][:19], r["kind"], str(r["items_processed"]), str(r["duration_ms"]), details_str)
    console.print(table)


def _handle_turn(core: EidosCore, user_input: str) -> None:
    try:
        response = core.think_and_respond(user_input)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        logger.error("eidos_turn_error", error=str(e))
        return

    # Respuesta principal
    console.print(Panel(response.text, title="[bold blue]eidos>[/]", border_style="blue"))

    # Traza
    memory_hits = len(response.memory_context) if response.memory_context else 0
    reward_color = "green" if response.reward_delta >= 0 else "red"
    console.print(
        Panel(
            Syntax(
                f'{{"monologue_id": "{response.monologue_id}", '
                f'"route": "{response.route_type}", '
                f'"confidence": {response.confidence}, '
                f'"memory_hits": {memory_hits}, '
                f'"reward_delta": {response.reward_delta:+.4f}}}',
                "json",
                theme="ansi_dark",
                word_wrap=True,
            ),
            title="[dim]trace[/]",
            border_style="dim",
        )
    )
    console.print(f"[{reward_color}]reward Δ {response.reward_delta:+.4f}[/{reward_color}]")


if __name__ == "__main__":
    main()
