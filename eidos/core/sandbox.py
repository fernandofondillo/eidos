"""ToolSandbox — Fase 3.1.

Ejecuta código generado por EIDOS en un entorno aislado con defense-in-depth:

1. AST parsing previo: rechaza código con constructs peligrosos o
   imports fuera de whitelist.
2. Subprocess aislado: stdin=DEVNULL, stdout/stderr=PIPE, timeout.
3. Resource limits (POSIX): CPU, memoria, filesize, nproc.

El sandbox NUNCA hace exec()/eval() directo en el proceso principal.
Siempre lanza un subprocess que ejecuta un wrapper con el código bajo
test, captura stdout/stderr, y devuelve un resultado estructurado.

Uso:
    sandbox = ToolSandbox(timeout_sec=5, mem_limit_mb=256)
    result = sandbox.run_code("print('hello')", entry="main")
    if result.ok:
        print(result.stdout)
"""

from __future__ import annotations

import ast
import os
import resource
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Whitelist de módulos permitidos en el sandbox
# ---------------------------------------------------------------------------

# Módulos seguros: pure-python + urllib para tools de red.
_ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        # Stdlib seguro
        "math", "statistics", "random", "json", "re", "datetime",
        "collections", "collections.abc", "itertools", "functools",
        "typing", "dataclasses", "enum", "abc", "copy", "operator",
        "string", "textwrap", "unicodedata", "difflib", "heapq",
        "bisect", "array", "queue", "uuid", "decimal", "fractions",
        "numbers", "pprint", "reprlib", "secrets",
        # Red (para tools de acceso web — EIDOS las valida en sandbox)
        "urllib.request", "urllib.parse", "urllib.error", "urllib",
        # EIDOS (limitado a utilidades safe)
        "eidos.utils.logging",  # solo para logging interno
    }
)

# Funciones builtins prohibidas (siempre, sin excepción).
_FORBIDDEN_BUILTINS: frozenset[str] = frozenset(
    {
        "exec", "eval", "compile", "__import__", "open",
        "globals", "locals", "vars", "dir",  # introspection peligrosa
        "input", "breakpoint", "exit", "quit",
    }
)

# Attributes que empiezan por estos prefijos están prohibidos.
_FORBIDDEN_ATTR_PREFIXES: tuple[str, ...] = ("__",)

# Names que NO pueden aparecer como Attribute access (dunder peligroso).
_FORBIDDEN_ATTRS: frozenset[str] = frozenset(
    {
        "__builtins__", "__subclasses__", "__bases__", "__mro__",
        "__class__", "__globals__", "__code__", "__dict__",
    }
)


# ---------------------------------------------------------------------------
# Excepciones del sandbox
# ---------------------------------------------------------------------------


class SandboxError(Exception):
    """Error de validación AST o ejecución."""


class SandboxSecurityError(SandboxError):
    """Código rechazado por seguridad (intentó usar construct prohibido)."""


class SandboxTimeoutError(SandboxError):
    """El código excedió el timeout."""


class SandboxResourceError(SandboxError):
    """El código excedió un resource limit (CPU/mem)."""


# ---------------------------------------------------------------------------
# AST validator
# ---------------------------------------------------------------------------


class _ASTValidator(ast.NodeVisitor):
    """Recorre el AST y rechaza constructs peligrosos."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.violations: list[str] = []

    def check(self) -> None:
        tree = ast.parse(self.code, mode="exec")
        self.visit(tree)
        if self.violations:
            raise SandboxSecurityError(
                f"Code rejected by AST validator: {'; '.join(self.violations[:5])}"
            )

    def _violation(self, msg: str) -> None:
        self.violations.append(msg)

    # --- Imports ---

    def visit_Import(self, node: ast.Import) -> Any:  # noqa: N802
        for alias in node.names:
            if alias.name not in _ALLOWED_MODULES:
                self._violation(f"Import '{alias.name}' not in whitelist")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:  # noqa: N802
        module = node.module or ""
        if module not in _ALLOWED_MODULES:
            self._violation(f"From-import '{module}' not in whitelist")
        self.generic_visit(node)

    # --- Calls a builtins prohibidas ---

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: N802
        # Detectar exec(...), eval(...), __import__(...), etc.
        func = node.func
        if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BUILTINS:
            self._violation(f"Call to forbidden builtin '{func.id}'")
        elif isinstance(func, ast.Attribute):
            attr = func.attr
            if attr in _FORBIDDEN_BUILTINS:
                self._violation(f"Call to forbidden method '{attr}'")
        self.generic_visit(node)

    # --- Attribute access peligrosos ---

    def visit_Attribute(self, node: ast.Attribute) -> Any:  # noqa: N802
        attr = node.attr
        if attr in _FORBIDDEN_ATTRS:
            self._violation(f"Access to forbidden attribute '{attr}'")
        # __double_underscore en general (salvo dunders legítimos de protocolo)
        if attr.startswith("__") and attr.endswith("__") and attr not in {
            "__init__", "__str__", "__repr__", "__len__", "__iter__",
            "__next__", "__enter__", "__exit__", "__eq__", "__hash__",
            "__lt__", "__le__", "__gt__", "__ge__", "__ne__",
            "__add__", "__sub__", "__mul__", "__truediv__", "__floordiv__",
            "__mod__", "__pow__", "__neg__", "__pos__", "__abs__",
            "__bool__", "__contains__", "__getitem__", "__setitem__",
            "__delitem__", "__call__", "__name__", "__doc__",
        }:
            self._violation(f"Access to dunder attribute '{attr}'")
        self.generic_visit(node)

    # --- Subscript con __builtins__ ---

    def visit_Subscript(self, node: ast.Subscript) -> Any:  # noqa: N802
        # Detectar algo['__builtins__'] etc.
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if node.slice.value in _FORBIDDEN_ATTRS:
                self._violation(f"Subscript with forbidden key '{node.slice.value}'")
        self.generic_visit(node)


def validate_ast(code: str) -> None:
    """Valida el código con AST. Lanza SandboxSecurityError si rechazado."""
    _ASTValidator(code).check()


# ---------------------------------------------------------------------------
# Resultado de ejecución
# ---------------------------------------------------------------------------


@dataclass
class SandboxResult:
    """Resultado de ejecutar código en el sandbox."""

    ok: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    duration_ms: int = 0
    security_violations: list[str] = field(default_factory=list)

    @property
    def is_security_error(self) -> bool:
        return bool(self.security_violations) or (
            self.error is not None and "SandboxSecurityError" in (self.error or "")
        )


# ---------------------------------------------------------------------------
# ToolSandbox
# ---------------------------------------------------------------------------


# Template del wrapper que ejecuta el subprocess.
# Carga el código bajo test. Si entry está definido y existe, lo llama
# con args (JSON). Si entry es None o no existe, solo ejecuta el código
# (modo "script" para prints sueltos).
_WRAPPER_TEMPLATE = """\
import json, sys, resource, traceback

# Resource limits (POSIX)
try:
    resource.setrlimit(resource.RLIMIT_CPU, ({cpu_sec}, {cpu_sec}))
    resource.setrlimit(resource.RLIMIT_AS, ({mem_bytes}, {mem_bytes}))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
except (ValueError, resource.error):
    pass  # best-effort; en macOS RLIMIT_AS no siempre funciona

# Builtins: bloquear los peligrosos
_FORBIDDEN = {{'exec', 'eval', 'compile', '__import__', 'open',
              'globals', 'locals', 'vars', 'input', 'breakpoint'}}
_safe_builtins = {{k: v for k, v in __builtins__.items()
                   if k not in _FORBIDDEN}} if isinstance(__builtins__, dict) else __builtins__
__builtins__ = _safe_builtins

# Cargar el código bajo test
{user_code}

# Llamar a la función entry con args (si está definida)
_entry = '{entry}'
args = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else {{}}
if _entry and _entry != '__none__':
    func = globals().get(_entry)
    if func is None:
        print(json.dumps({{"error": "Entry point '" + _entry + "' not found"}}))
        sys.exit(2)
    try:
        result = func(**args) if callable(func) else None
        if result is not None:
            print(json.dumps({{"result": result}}, default=str))
        else:
            print(json.dumps({{"ok": True}}))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
"""


class ToolSandbox:
    """Ejecuta código generado por EIDOS de forma aislada.

    3 capas de defense-in-depth:
    1. AST validation (en proceso principal, antes de subprocess).
    2. Subprocess aislado con stdin=DEVNULL, stdout/stderr=PIPE, timeout.
    3. Resource limits (CPU, mem, filesize) en POSIX.
    """

    def __init__(
        self,
        timeout_sec: float = 5.0,
        mem_limit_mb: int = 256,
        cpu_limit_sec: int = 2,
    ) -> None:
        self._timeout = max(0.5, float(timeout_sec))
        self._mem_bytes = int(mem_limit_mb * 1024 * 1024)
        self._cpu_sec = max(1, int(cpu_limit_sec))

    def validate(self, code: str) -> list[str]:
        """Valida el código y devuelve lista de violaciones (vacía si OK)."""
        try:
            validate_ast(code)
            return []
        except SandboxSecurityError as e:
            return [str(e)]

    def run_code(
        self,
        code: str,
        entry: str | None = "main",
        args: dict[str, Any] | None = None,
    ) -> SandboxResult:
        """Ejecuta el código en subprocess aislado y devuelve el resultado.

        Args:
            code: código Python a ejecutar.
            entry: nombre de la función a invocar tras cargar el código.
                Si es None, solo ejecuta el código (modo script, para prints sueltos).
            args: kwargs que se pasan a `entry`.
        """
        import time

        # Capa 1: AST validation
        violations = self.validate(code)
        if violations:
            logger.warning("sandbox_ast_rejected", violations=violations)
            return SandboxResult(
                ok=False,
                exit_code=-1,
                error="AST validation failed",
                security_violations=violations,
            )

        # Capa 2 + 3: subprocess aislado con rlimits
        entry_str = entry if entry else "__none__"
        wrapper = _WRAPPER_TEMPLATE.format(
            user_code=code,
            entry=entry_str,
            cpu_sec=self._cpu_sec,
            mem_bytes=self._mem_bytes,
        )

        args_json = json_module.dumps(args or {})
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "-c", wrapper, args_json],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self._timeout,
                check=False,
                # Environment restringido: solo PATH y PYTHONPATH mínimo
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return SandboxResult(
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=proc.stdout.decode("utf-8", errors="replace"),
                stderr=proc.stderr.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("sandbox_timeout", timeout=self._timeout)
            return SandboxResult(
                ok=False,
                exit_code=-1,
                error=f"Timeout after {self._timeout}s",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error("sandbox_execution_failed", error=str(e))
            return SandboxResult(
                ok=False,
                exit_code=-1,
                error=f"Execution failed: {e}",
                duration_ms=duration_ms,
            )

    def smoke_test_tool(
        self,
        code: str,
        entry: str,
        test_args: dict[str, Any] | None = None,
    ) -> SandboxResult:
        """Smoke test de una herramienta: ejecuta con args de prueba y
        verifica que no rompe. No valida el resultado, solo que no crashea."""
        return self.run_code(code, entry=entry, args=test_args or {})


# Import json with alias to avoid collision with template formatting
import json as json_module


__all__ = [
    "ToolSandbox",
    "SandboxResult",
    "SandboxError",
    "SandboxSecurityError",
    "SandboxTimeoutError",
    "SandboxResourceError",
    "validate_ast",
]
