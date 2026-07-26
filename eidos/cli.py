"""CLI de EIDOS — Fase 2.

REPL con memoria cognitiva, motivación intrínseca, consolidación
background y Cortex Hub (modelos locales GGUF + fallback API).

Uso:
    uv run eidos                       # REPL interactivo
    uv run eidos --once "..."          # una sola consulta
    uv run eidos stats                 # estadísticas de las 5 capas
    uv run eidos motivation            # métricas de reward signal
    uv run eidos consolidate           # consolidación manual
    uv run eidos runs                  # historial de consolidation_runs
    uv run eidos models list           # modelos registrados
    uv run eidos models download ID    # descargar modelo
    uv run eidos models delete ID      # eliminar modelo
    uv run eidos cortex status         # estado del CortexHub
    uv run eidos cortex verify         # verificar SHA256 de modelos
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
from eidos.cortex.hub import CortexHub
from eidos.cortex.manager import ModelManager
from eidos.cortex.privacy import PrivacyFilter
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
    cortex_cfg = config.get("cortex", {})
    evolution_cfg = config.get("evolution", {})
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

    # Fase 2: CortexHub (si está habilitado)
    cortex_hub = None
    if cortex_cfg.get("enabled", False):
        models_dir = project_root / cortex_cfg.get("models_dir", "models")
        mm = ModelManager(db_path=db_path, models_dir=models_dir)
        cortex_hub = CortexHub(model_manager=mm)

    # Resolver backend según config
    backend_requested = core_cfg.get("monologue_backend", "stub")
    if cortex_hub is not None and backend_requested == "stub":
        # Si hay CortexHub, usar 'auto' (degradará a stub si no hay modelos)
        backend_requested = "auto"

    # Fase 3: CapsuleForge + EvolutionLoop
    evolution_loop = None
    if evolution_cfg.get("enabled", True):  # activo por defecto
        from eidos.core.forge import CapsuleForge, StubForgeBackend
        from eidos.core.evolution import EvolutionLoop
        from eidos.core.sandbox import ToolSandbox

        sandbox = ToolSandbox(
            timeout_sec=float(evolution_cfg.get("sandbox_timeout_sec", 5)),
            mem_limit_mb=int(evolution_cfg.get("sandbox_mem_mb", 256)),
        )
        # Backend del forge: stub por defecto; LLM si hay cortex_hub
        forge_backend = StubForgeBackend()
        if cortex_hub is not None:
            from eidos.core.forge import LLMForgeBackend
            forge_backend = LLMForgeBackend(cortex_hub=cortex_hub, sandbox=sandbox)

        forge = CapsuleForge(
            db_path=db_path,
            procedural=memory.procedural,
            backend=forge_backend,
            sandbox=sandbox,
        )
        evolution_loop = EvolutionLoop(
            forge=forge,
            procedural=memory.procedural,
            auto_forge=bool(evolution_cfg.get("auto_forge", True)),
        )

    return EidosCore(
        monologue_backend=backend_requested,
        confidence_threshold=float(core_cfg.get("confidence_threshold", 0.6)),
        monologues_dir=monologues_dir,
        max_plan_steps=int(core_cfg.get("max_plan_steps", 5)),
        memory=memory,
        motivation=motivation,
        consolidator=consolidator,
        auto_start_consolidator=start_consolidator,
        cortex_hub=cortex_hub,
        evolution_loop=evolution_loop,
    )


# ---------------------------------------------------------------------------
# CLI principal
# ---------------------------------------------------------------------------


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

    # Panel de estado inicial
    cortex_status = "off"
    if core._cortex_hub is not None:
        cortex_status = "on (lock: " + ("yes" if core._cortex_hub.has_lock() else "no") + ")"

    console.print(
        Panel.fit(
            f"[bold cyan]EIDOS[/] v{__version__}\n"
            f"Backend: [yellow]{core._effective_backend}[/]\n"
            f"Memoria: [green]5 capas activas[/]\n"
            f"Motivación: [magenta]reward signal ON[/]\n"
            f"Consolidador: [{'green' if core._consolidator and core._consolidator.is_running() else 'red'}]"
            f"{'running' if core._consolidator and core._consolidator.is_running() else 'stopped'}[/]\n"
            f"Cortex Hub: [{'green' if cortex_status != 'off' else 'red'}]{cortex_status}[/]\n"
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


# ---------------------------------------------------------------------------
# Subcomandos: stats, motivation, consolidate, runs (Fase 1)
# ---------------------------------------------------------------------------


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
    """Muestra estadísticas del reward signal."""
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


# ---------------------------------------------------------------------------
# Subcomandos: models (Fase 2)
# ---------------------------------------------------------------------------


@main.group()
@click.pass_context
def models(ctx: click.Context) -> None:
    """Gestión de modelos GGUF/ONNX locales."""
    pass


@models.command(name="list")
@click.pass_context
def models_list(ctx: click.Context) -> None:
    """Lista todos los modelos registrados."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)
    cortex_cfg = config.get("cortex", {})
    models_dir = project_root / cortex_cfg.get("models_dir", "models")

    mm = ModelManager(db_path=memory.db_path, models_dir=models_dir)
    all_models = mm.list_all()

    if not all_models:
        console.print("[dim]No hay modelos registrados. Usa 'eidos models register' (próximamente) o edita config.[/]")
        return

    table = Table(title=f"📦 Modelos registrados ({len(all_models)})", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold")
    table.add_column("Name", style="white")
    table.add_column("Purpose", style="yellow")
    table.add_column("Status", style="magenta")
    table.add_column("Size", style="dim")
    table.add_column("Quant", style="dim")
    for m in all_models:
        size_str = f"{m.size_bytes / 1024 / 1024:.1f} MB" if m.size_bytes else "-"
        table.add_row(m.id, m.name, m.purpose, m.status, size_str, m.quantization or "-")
    console.print(table)


@models.command(name="download")
@click.argument("model_id")
@click.option("--force", is_flag=True, help="Forzar redescarga.")
@click.pass_context
def models_download(ctx: click.Context, model_id: str, force: bool) -> None:
    """Descarga un modelo registrado."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="INFO", format="console")
    memory = MemoryStore.from_config(config, project_root)
    cortex_cfg = config.get("cortex", {})
    models_dir = project_root / cortex_cfg.get("models_dir", "models")

    mm = ModelManager(db_path=memory.db_path, models_dir=models_dir)
    info = mm.get(model_id)
    if info is None:
        console.print(f"[red]Modelo '{model_id}' no registrado.[/]")
        return

    console.print(f"[cyan]Descargando {info.name}...[/]")
    try:
        path = mm.download(model_id, force=force)
        console.print(f"[green]✓ Descargado en: {path}[/]")
        console.print(f"  Tamaño: [yellow]{path.stat().st_size / 1024 / 1024:.1f} MB[/]")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/]")


@models.command(name="delete")
@click.argument("model_id")
@click.pass_context
def models_delete(ctx: click.Context, model_id: str) -> None:
    """Elimina un modelo (archivo + registro)."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)
    cortex_cfg = config.get("cortex", {})
    models_dir = project_root / cortex_cfg.get("models_dir", "models")

    mm = ModelManager(db_path=memory.db_path, models_dir=models_dir)
    if mm.delete(model_id):
        console.print(f"[green]✓ Modelo '{model_id}' eliminado.[/]")
    else:
        console.print(f"[red]Modelo '{model_id}' no encontrado.[/]")


# ---------------------------------------------------------------------------
# Subcomandos: cortex (Fase 2)
# ---------------------------------------------------------------------------


@main.group()
@click.pass_context
def cortex(ctx: click.Context) -> None:
    """Estado y gestión del CortexHub."""
    pass


@cortex.command(name="status")
@click.pass_context
def cortex_status(ctx: click.Context) -> None:
    """Estado del CortexHub."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)
    cortex_cfg = config.get("cortex", {})
    models_dir = project_root / cortex_cfg.get("models_dir", "models")

    mm = ModelManager(db_path=memory.db_path, models_dir=models_dir)
    hub = CortexHub(model_manager=mm)
    s = hub.stats()

    table = Table(title="🧩 EIDOS — CortexHub Status", show_header=True, header_style="bold cyan")
    table.add_column("Métrica", style="bold")
    table.add_column("Valor", style="white")
    table.add_row("Lock path", s["lock_path"])
    table.add_row("Has lock", "✓" if s["has_lock"] else "✗")
    table.add_row("Monologue backend active", "✓" if s["monologue_backend_active"] else "✗")
    table.add_row("Embedder active", "✓" if s["embedder_active"] else "✗")
    table.add_row("Disk usage", f"{s['models']['disk_usage_bytes'] / 1024 / 1024:.1f} MB")
    console.print(table)

    by_status = s["models"]["by_status"]
    if by_status:
        stable = Table(title="Modelos por estado", show_header=True, header_style="bold cyan")
        stable.add_column("Estado", style="bold")
        stable.add_column("Count", style="white")
        stable.add_column("Size", style="dim")
        for status, m in by_status.items():
            size_mb = m["size_bytes"] / 1024 / 1024 if m["size_bytes"] else 0
            stable.add_row(status, str(m["count"]), f"{size_mb:.1f} MB" if size_mb > 0 else "-")
        console.print(stable)


@cortex.command(name="verify")
@click.pass_context
def cortex_verify(ctx: click.Context) -> None:
    """Verifica SHA256 de todos los modelos READY."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)
    cortex_cfg = config.get("cortex", {})
    models_dir = project_root / cortex_cfg.get("models_dir", "models")

    mm = ModelManager(db_path=memory.db_path, models_dir=models_dir)
    all_models = mm.list_all()
    if not all_models:
        console.print("[dim]No hay modelos registrados.[/]")
        return

    table = Table(title="🔍 Verificación SHA256", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold")
    table.add_column("Status", style="white")
    table.add_column("Verify", style="white")
    for m in all_models:
        if m.status == "ready":
            ok = mm.verify(m.id)
            verify_str = "[green]✓ OK[/]" if ok else "[red]✗ CORRUPT[/]"
        else:
            verify_str = "[dim]N/A[/]"
        table.add_row(m.id, m.status, verify_str)
    console.print(table)


@cortex.command(name="privacy-test")
@click.argument("text")
def cortex_privacy_test(text: str) -> None:
    """Prueba el PrivacyFilter sobre un texto."""
    pf = PrivacyFilter()
    result = pf.filter(text)
    console.print(
        Panel(
            f"[bold]Original:[/]\n{text}\n\n"
            f"[bold]Filtrado:[/]\n{result.filtered_text}\n\n"
            f"[bold]Redactions:[/]\n{result.redactions_count}",
            title="🔒 PrivacyFilter test",
            border_style="magenta",
        )
    )


# ---------------------------------------------------------------------------
# Subcomandos: capsules (Fase 3)
# ---------------------------------------------------------------------------


@main.group()
@click.pass_context
def capsules(ctx: click.Context) -> None:
    """Gestión de cápsulas cognitivas (.eidos)."""
    pass


@capsules.command(name="list")
@click.option("--status", default=None, help="Filtrar por status (pending, approved, rejected, auto_approved).")
@click.pass_context
def capsules_list(ctx: click.Context, status: str | None) -> None:
    """Lista cápsulas y drafts."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)

    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=memory.db_path,
        procedural=memory.procedural,
        backend=StubForgeBackend(),
    )

    # Drafts
    drafts = forge.list_drafts(status=status)
    if drafts:
        dtable = Table(title=f"📝 Drafts ({len(drafts)})", show_header=True, header_style="bold yellow")
        dtable.add_column("ID", style="dim")
        dtable.add_column("Name", style="bold")
        dtable.add_column("Status", style="yellow")
        dtable.add_column("Confidence", style="white")
        dtable.add_column("Smoke", style="white")
        for d in drafts:
            dtable.add_row(
                d["id"][:8],
                d["name"],
                d["status"],
                f"{d['genesis_confidence']:.2f}",
                "✓" if d["smoke_test_passed"] else "✗",
            )
        console.print(dtable)
    else:
        console.print("[dim]No hay drafts.[/]")

    # Cápsulas activas
    all_caps = memory.procedural.list_all()
    if all_caps:
        ctable = Table(title=f"📦 Cápsulas activas ({len(all_caps)})", show_header=True, header_style="bold cyan")
        ctable.add_column("ID", style="dim")
        ctable.add_column("Name", style="bold")
        ctable.add_column("Ver", style="white")
        ctable.add_column("Uses", style="yellow")
        ctable.add_column("Fav", style="magenta")
        ctable.add_column("TTL", style="dim")
        for c in all_caps:
            ctable.add_row(
                c.id[:8],
                c.name,
                c.version,
                str(c.uses),
                "★" if c.favorite else "",
                f"{c.ttl_days}d",
            )
        console.print(ctable)
    else:
        console.print("[dim]No hay cápsulas activas.[/]")


@capsules.command(name="forge")
@click.argument("request")
@click.option("--force-pending", is_flag=True, help="Forzar que quede pendiente de aprobación.")
@click.pass_context
def capsules_forge(ctx: click.Context, request: str, force_pending: bool) -> None:
    """Forja una nueva cápsula a partir de una petición NL."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="INFO", format="console")
    memory = MemoryStore.from_config(config, project_root)

    from eidos.core.forge import CapsuleForge, StubForgeBackend
    from eidos.core.sandbox import ToolSandbox

    forge = CapsuleForge(
        db_path=memory.db_path,
        procedural=memory.procedural,
        backend=StubForgeBackend(),
        sandbox=ToolSandbox(),
    )
    draft, decision = forge.forge(request, force_pending=force_pending)

    console.print(
        Panel(
            f"[bold]ID:[/] {draft.id}\n"
            f"[bold]Name:[/] {draft.name}\n"
            f"[bold]Domain:[/] {draft.ontology.domain}\n"
            f"[bold]Confidence:[/] {draft.genesis_confidence:.2f}\n"
            f"[bold]Smoke test:[/] {'✓' if draft.smoke_test_passed else '✗'}\n"
            f"[bold]Decision:[/] [yellow]{decision.value}[/]\n"
            f"[bold]Tools:[/] {len(draft.tools)}",
            title="🔨 Cápsula forjada",
            border_style="green" if decision.value == "auto_approved" else "yellow",
        )
    )
    if draft.smoke_test_output:
        console.print(f"[dim]Smoke test output:[/]\n{draft.smoke_test_output}")


@capsules.command(name="approve")
@click.argument("draft_id")
@click.pass_context
def capsules_approve(ctx: click.Context, draft_id: str) -> None:
    """Aprueba un draft pendiente → lo promueve a cápsula activa."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="INFO", format="console")
    memory = MemoryStore.from_config(config, project_root)

    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=memory.db_path,
        procedural=memory.procedural,
        backend=StubForgeBackend(),
    )
    # Permitir IDs parciales (primer match)
    drafts = forge.list_drafts()
    match = next((d for d in drafts if d["id"].startswith(draft_id)), None)
    if match is None:
        console.print(f"[red]Draft '{draft_id}' no encontrado.[/]")
        return
    ok = forge.approve(match["id"])
    if ok:
        console.print(f"[green]✓ Draft {match['id'][:8]} aprobado y promovido a cápsula activa.[/]")
    else:
        console.print(f"[red]No se pudo aprobar el draft {match['id'][:8]}.[/]")


@capsules.command(name="reject")
@click.argument("draft_id")
@click.pass_context
def capsules_reject(ctx: click.Context, draft_id: str) -> None:
    """Rechaza un draft pendiente."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)

    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=memory.db_path,
        procedural=memory.procedural,
        backend=StubForgeBackend(),
    )
    drafts = forge.list_drafts()
    match = next((d for d in drafts if d["id"].startswith(draft_id)), None)
    if match is None:
        console.print(f"[red]Draft '{draft_id}' no encontrado.[/]")
        return
    ok = forge.reject(match["id"])
    if ok:
        console.print(f"[green]✓ Draft {match['id'][:8]} rechazado.[/]")
    else:
        console.print(f"[red]No se pudo rechazar el draft.[/]")


@capsules.command(name="favorite")
@click.argument("capsule_id")
@click.pass_context
def capsules_favorite(ctx: click.Context, capsule_id: str) -> None:
    """Marca una cápsula como favorita (nunca expira)."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)

    all_caps = memory.procedural.list_all()
    match = next((c for c in all_caps if c.id.startswith(capsule_id)), None)
    if match is None:
        console.print(f"[red]Cápsula '{capsule_id}' no encontrada.[/]")
        return
    memory.procedural.set_favorite(match.id, True)
    console.print(f"[green]✓ Cápsula '{match.name}' marcada como favorita ★[/]")


@capsules.command(name="evolution")
@click.pass_context
def capsules_evolution(ctx: click.Context) -> None:
    """Estadísticas del EvolutionLoop."""
    obj = ctx.obj or {}
    config = obj.get("config") or load_config(None)
    project_root = obj.get("project_root") or DEFAULT_CONFIG_PATH.resolve().parent.parent
    configure_logging(level="WARNING", format="console")
    memory = MemoryStore.from_config(config, project_root)

    from eidos.core.evolution import EvolutionLoop
    from eidos.core.forge import CapsuleForge, StubForgeBackend

    forge = CapsuleForge(
        db_path=memory.db_path,
        procedural=memory.procedural,
        backend=StubForgeBackend(),
    )
    evo = EvolutionLoop(forge=forge, procedural=memory.procedural)
    s = evo.stats()

    table = Table(title="🧬 EIDOS — Evolution Stats", show_header=True, header_style="bold green")
    table.add_column("Métrica", style="bold")
    table.add_column("Valor", style="white")
    table.add_row("Auto-forge", "✓ ON" if s["auto_forge_enabled"] else "✗ OFF")
    table.add_row("Cápsulas totales", str(s["total_capsules"]))
    table.add_row("Favoritas", str(s["favorites"]))
    table.add_row("Candidatas a promoción", str(s["promotion_candidates"]))
    table.add_row("Threshold promoción", f"{s['promotion_threshold']} usos / {s['promotion_window_hours']}h")
    console.print(table)

    # Ejecutar check_promotions para mostrar/realizar promociones
    promoted = evo.check_promotions()
    if promoted:
        console.print(f"\n[green]✓ {len(promoted)} cápsula(s) promovida(s) a favorita esta ejecución.[/]")
    else:
        console.print("\n[dim]No hay promociones pendientes.[/]")


@capsules.command(name="sandbox-test")
@click.argument("code", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, path_type=Path), default=None, help="Leer código desde archivo.")
@click.option("--entry", default="main", help="Función entry point.")
@click.pass_context
def capsules_sandbox_test(ctx: click.Context, code: str | None, file_path: Path | None, entry: str) -> None:
    """Prueba el ToolSandbox con código Python."""
    from eidos.core.sandbox import ToolSandbox

    if file_path:
        code = file_path.read_text(encoding="utf-8")
    elif not code:
        console.print("[red]Debes pasar CODE o --file PATH.[/]")
        return

    sb = ToolSandbox(timeout_sec=5)
    result = sb.run_code(code, entry=entry if entry != "none" else None)
    console.print(
        Panel(
            f"[bold]OK:[/] {'✓' if result.ok else '✗'}\n"
            f"[bold]Exit code:[/] {result.exit_code}\n"
            f"[bold]Duration:[/] {result.duration_ms} ms\n"
            f"[bold]Security violations:[/] {len(result.security_violations)}",
            title="🧪 Sandbox test",
            border_style="green" if result.ok else "red",
        )
    )
    if result.stdout:
        console.print(f"[bold]stdout:[/]\n{result.stdout}")
    if result.stderr:
        console.print(f"[bold red]stderr:[/]\n{result.stderr}")
    if result.security_violations:
        console.print(f"[bold red]Violations:[/]")
        for v in result.security_violations:
            console.print(f"  • {v}")


# ---------------------------------------------------------------------------
# Handler de turnos
# ---------------------------------------------------------------------------


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
                f'"backend": "{response.monologue_backend}", '
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

    # Fase 3: si el turno disparó génesis de cápsula
    if response.evolution_event:
        ev = response.evolution_event
        ev_color = "green" if ev.get("decision") == "auto_approved" else "yellow"
        console.print(
            Panel(
                f"[bold]Topic:[/] {ev.get('topic', '?')}\n"
                f"[bold]Decision:[/] [{ev_color}]{ev.get('decision', '?')}[/{ev_color}]\n"
                + (f"[bold]Draft ID:[/] {ev.get('draft_id', '?')[:8]}\n" if ev.get("draft_id") else "")
                + (f"[bold]Name:[/] {ev.get('name', '?')}\n" if ev.get("name") else "")
                + (f"[bold]Confidence:[/] {ev.get('confidence', 0):.2f}\n" if ev.get("confidence") else "")
                + (f"[dim]{ev.get('error')}[/]" if ev.get("error") else ""),
                title="🧬 Evolution triggered",
                border_style=ev_color,
            )
        )


if __name__ == "__main__":
    main()
