"""Tests del ToolSandbox — Fase 3.1.

Tests con defense-in-depth: AST validation + subprocess aislado + rlimits.
Verificamos que código peligroso es rechazado Y que código seguro se ejecuta.
"""

from __future__ import annotations

import pytest

from eidos.core.sandbox import (
    SandboxResult,
    SandboxSecurityError,
    ToolSandbox,
    validate_ast,
)


# ---------------------------------------------------------------------------
# AST Validation — rechazo de constructs peligrosos
# ---------------------------------------------------------------------------


class TestASTValidation:
    def test_safe_code_passes(self) -> None:
        validate_ast("import math\nx = math.sqrt(16)\nprint(x)")

    def test_exec_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="exec"):
            validate_ast("exec('print(1)')")

    def test_eval_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="eval"):
            validate_ast("x = eval('1+1')")

    def test_compile_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="compile"):
            validate_ast("code = compile('x=1', '<s>', 'exec')")

    def test_dunder_import_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="__import__"):
            validate_ast("os = __import__('os')")

    def test_open_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="open"):
            validate_ast("f = open('/etc/passwd')")

    def test_os_import_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="not in whitelist"):
            validate_ast("import os")

    def test_subprocess_import_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="not in whitelist"):
            validate_ast("import subprocess")

    def test_socket_import_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="not in whitelist"):
            validate_ast("import socket")

    def test_from_os_import_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="not in whitelist"):
            validate_ast("from os import system")

    def test_dunder_builtins_access_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="__builtins__"):
            validate_ast("x = obj.__builtins__")

    def test_subclasses_access_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="__subclasses__"):
            validate_ast("subs = object.__subclasses__()")

    def test_globals_call_rejected(self) -> None:
        with pytest.raises(SandboxSecurityError, match="globals"):
            validate_ast("g = globals()")

    def test_allowed_modules_pass(self) -> None:
        # math, json, datetime, re son permitidos
        validate_ast("import math\nimport json\nimport re\nimport datetime")

    def test_safe_dunder_methods_pass(self) -> None:
        # __init__, __str__ etc. son protocolos legítimos
        validate_ast(
            """
class Foo:
    def __init__(self):
        self.x = 1
    def __str__(self):
        return str(self.x)
    def __len__(self):
        return 1
"""
        )


# ---------------------------------------------------------------------------
# Ejecución — código seguro se ejecuta correctamente
# ---------------------------------------------------------------------------


class TestSafeExecution:
    def test_simple_print(self) -> None:
        sb = ToolSandbox(timeout_sec=3, mem_limit_mb=64, cpu_limit_sec=1)
        # Sin entry point → modo script
        result = sb.run_code("print('hello sandbox')\n", entry=None)
        assert result.ok is True
        assert "hello sandbox" in result.stdout

    def test_entry_point_called(self) -> None:
        code = """
def main(name='world'):
    return f'Hello, {name}!'
"""
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code(code, entry="main", args={"name": "EIDOS"})
        assert result.ok is True
        # El wrapper imprime el resultado en JSON
        assert "EIDOS" in result.stdout

    def test_math_computation(self) -> None:
        code = """
import math

def main():
    return math.factorial(10)
"""
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code(code, entry="main", args={})
        assert result.ok is True
        assert "3628800" in result.stdout

    def test_exception_caught(self) -> None:
        code = """
def main():
    raise ValueError('test error')
"""
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code(code, entry="main", args={})
        assert result.ok is False
        assert "test error" in result.stderr

    def test_entry_not_found(self) -> None:
        code = "x = 1"
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code(code, entry="nonexistent", args={})
        assert result.ok is False
        assert "not found" in result.stdout.lower() or "entry" in result.stdout.lower()

    def test_no_entry_mode_script(self) -> None:
        # entry=None → solo ejecuta el código, no busca función
        code = "x = 6 * 7\nprint(f'result: {x}')"
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code(code, entry=None)
        assert result.ok is True
        assert "result: 42" in result.stdout


# ---------------------------------------------------------------------------
# Ejecución — código peligroso es rechazado ANTES del subprocess
# ---------------------------------------------------------------------------


class TestDangerousCodeRejected:
    def test_exec_rejected_before_execution(self) -> None:
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code("exec('import os')", entry="main")
        assert result.ok is False
        assert result.is_security_error is True
        assert len(result.security_violations) > 0

    def test_os_import_rejected(self) -> None:
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code("import os\nos.system('echo hacked')", entry="main")
        assert result.ok is False
        assert result.is_security_error is True

    def test_subprocess_rejected(self) -> None:
        code = """
import subprocess
def main():
    subprocess.run(['ls', '/'])
"""
        sb = ToolSandbox(timeout_sec=3)
        result = sb.run_code(code, entry="main")
        assert result.ok is False
        assert result.is_security_error is True


# ---------------------------------------------------------------------------
# Timeout y resource limits
# ---------------------------------------------------------------------------


class TestResourceLimits:
    def test_timeout_enforced(self) -> None:
        # Bucle infinito: debe agotar el timeout
        code = """
def main():
    while True:
        pass
"""
        sb = ToolSandbox(timeout_sec=1.5)
        result = sb.run_code(code, entry="main")
        assert result.ok is False
        assert "Timeout" in (result.error or "")

    def test_smoke_test_tool_passes(self) -> None:
        code = """
def greet(name='world'):
    return f'Hello, {name}!'
"""
        sb = ToolSandbox(timeout_sec=3)
        result = sb.smoke_test_tool(code, entry="greet", test_args={"name": "test"})
        assert result.ok is True

    def test_validate_returns_violations_list(self) -> None:
        sb = ToolSandbox(timeout_sec=3)
        # Código limpio → lista vacía
        assert sb.validate("import math\nx = 1") == []
        # Código peligroso → lista con violaciones
        violations = sb.validate("exec('x=1')")
        assert len(violations) > 0
        assert "exec" in violations[0]


# ---------------------------------------------------------------------------
# CLI smoke test del sandbox (vía validate_ast directo)
# ---------------------------------------------------------------------------


class TestSandboxResultProperties:
    def test_is_security_error_when_violations(self) -> None:
        result = SandboxResult(
            ok=False,
            exit_code=-1,
            error="AST validation failed",
            security_violations=["exec not allowed"],
        )
        assert result.is_security_error is True

    def test_is_security_error_false_when_normal_failure(self) -> None:
        result = SandboxResult(
            ok=False,
            exit_code=1,
            stderr="ValueError",
        )
        assert result.is_security_error is False
