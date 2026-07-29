"""EIDOS Response Layer — La voz de EIDOS.

Este módulo se ejecuta DESPUÉS del LLM, ANTES de enviar la respuesta al usuario.
Intercepta promesas vacías del LLM ("voy a buscar..."), ejecuta acciones reales,
y reescribe la respuesta en primera persona de EIDOS.

El LLM NUNCA habla directamente al usuario. EIDOS reformula todo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from eidos.core.monologue import Monologue
from eidos.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Action:
    kind: str  # 'code' | 'tool' | 'promise' | 'none'
    content: str = ""
    name: str = ""


@dataclass
class ActionResult:
    actions: list[Action] = field(default_factory=list)
    code_validated: bool = False
    code_valid: bool = False
    sandbox_output: str = ""
    tool_created: bool = False
    tool_name: str = ""
    promise_intercepted: bool = False
    errors: list[str] = field(default_factory=list)


class EidosResponseLayer:
    """Procesa la respuesta del LLM y la convierte en la voz de EIDOS."""

    # Patrones que indican que el LLM está prometiendo una acción que NO puede ejecutar
    _PROMISE_PATTERNS = [
        re.compile(r"(?i)(voy a\s+(?:buscar|ejecutar|lanzar|disparar|hacer|consultar|acceder))"),
        re.compile(r"(?i)(ahora mismo\s+(?:disparo|lanzo|ejecuto|consulto|busco))"),
        re.compile(r"(?i)(dame un (?:instante|segundo|momento))"),
        re.compile(r"(?i)(un segundo[,\s]*(?:mientras|espera))"),
        re.compile(r"(?i)(en cuanto llegue la respuesta)"),
        re.compile(r"(?i)(te paso (?:la|el)\s+\w+\s+(?:en|cuando))"),
    ]

    def __init__(self, sandbox: Any = None, memory: Any = None) -> None:
        self._sandbox = sandbox
        self._memory = memory

    def process(
        self,
        llm_response: str,
        monologue: Monologue,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Procesa la respuesta del LLM y devuelve la respuesta de EIDOS."""
        if not llm_response:
            return "EIDOS está procesando tu mensaje."

        ctx = context or {}
        user_input = ctx.get("user_input", "")

        # 1. Detectar acciones
        actions = self._detect_actions(llm_response)

        # 2. Ejecutar acciones
        result = self._execute_actions(actions, ctx)

        # 3. Reescribir en voz de EIDOS
        eidos_response = self._rewrite_in_eidos_voice(llm_response, monologue, result, ctx)

        return eidos_response

    def _detect_actions(self, response: str) -> list[Action]:
        """Detecta acciones en la respuesta del LLM."""
        actions: list[Action] = []

        # Detectar bloques de código ```python ... ```
        code_blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', response, re.DOTALL)
        for code in code_blocks:
            func_match = re.search(r'def\s+(\w+)\s*\(', code)
            name = func_match.group(1) if func_match else "funcion"
            actions.append(Action(kind="code", content=code.strip(), name=name))

        # Detectar promesas vacías ("voy a buscar...", "dame un segundo...")
        for pattern in self._PROMISE_PATTERNS:
            if pattern.search(response):
                actions.append(Action(kind="promise", content=pattern.pattern))
                break  # solo una detección por respuesta

        if not actions:
            actions.append(Action(kind="none"))

        return actions

    def _execute_actions(self, actions: list[Action], context: dict[str, Any]) -> ActionResult:
        """Ejecuta las acciones detectadas."""
        result = ActionResult(actions=actions)

        for action in actions:
            if action.kind == "code":
                # Validar en sandbox
                if self._sandbox is not None:
                    try:
                        sandbox_result = self._sandbox.run_code(action.content, entry=None)
                        result.code_validated = True

                        if sandbox_result.is_security_error:
                            result.code_valid = False
                            result.sandbox_output = f"Rechazado por seguridad: {sandbox_result.security_violations}"
                            result.errors.append(f"Seguridad: {sandbox_result.security_violations}")
                        else:
                            smoke = self._sandbox.smoke_test_tool(action.content, entry=action.name, test_args={})
                            if smoke.ok or smoke.exit_code == 2:
                                result.code_valid = True
                                result.sandbox_output = "Validado correctamente en sandbox."
                                result.tool_created = True
                                result.tool_name = action.name
                            else:
                                result.code_valid = False
                                result.sandbox_output = f"Error en ejecución: {smoke.stderr[:200]}"
                                result.errors.append(f"Ejecución: {smoke.stderr[:200]}")
                    except Exception as e:
                        result.code_validated = True
                        result.code_valid = False
                        result.sandbox_output = f"Error del sandbox: {e}"
                        result.errors.append(str(e))
                else:
                    result.code_validated = False
                    result.sandbox_output = "Sandbox no disponible."

            elif action.kind == "promise":
                # El LLM está prometiendo una acción que NO puede ejecutar.
                # EIDOS intercepta y lo prohíbe.
                result.promise_intercepted = True
                logger.warning("eidos_promise_intercepted", pattern=action.content[:80])

        return result

    def _rewrite_in_eidos_voice(
        self,
        llm_response: str,
        monologue: Monologue,
        action_result: ActionResult,
        context: dict[str, Any],
    ) -> str:
        """Reescribe la respuesta del LLM en primera persona de EIDOS."""
        has_code = any(a.kind == "code" for a in action_result.actions)
        has_promise = action_result.promise_intercepted

        # CASO 1: El LLM prometió una acción que no puede ejecutar
        if has_promise and not has_code:
            return (
                "No puedo ejecutar esa acción en este momento. "
                "No tengo una herramienta de acceso a internet activa aún. "
                "Si quieres que busque información en tiempo real, puedes pedirme "
                "que cree una herramienta de búsqueda web (escribe: 'crea una función "
                "que busque en internet') y la validaré en mi sandbox."
            )

        # CASO 2: Hay código y fue validado
        if has_code and action_result.code_validated:
            if action_result.code_valid:
                tool_name = action_result.tool_name or "la herramienta"
                clean_response = re.sub(r'```(?:python)?\s*\n.*?```', '', llm_response, flags=re.DOTALL).strip()
                eidos_text = (
                    f"He creado la herramienta '{tool_name}' y la he validado en mi sandbox. "
                    f"Funciona correctamente."
                )
                if clean_response:
                    eidos_text += f"\n\n{self._reformulate(clean_response)}"
                eidos_text += (
                    f"\n\nLa herramienta está disponible en tu panel de Cápsulas. "
                    f"Apruébala para que pueda usarla en futuras conversaciones."
                )
                return eidos_text
            else:
                return (
                    f"He intentado crear la herramienta, pero mi sandbox la ha rechazado.\n"
                    f"Motivo: {action_result.sandbox_output}\n\n"
                    f"Puedo intentar generarla de otra manera si me das más detalles."
                )

        # CASO 3: Hay código pero no se validó (sin sandbox)
        if has_code and not action_result.code_validated:
            clean_response = re.sub(r'```(?:python)?\s*\n.*?```', '', llm_response, flags=re.DOTALL).strip()
            return (
                f"He diseñado una herramienta basándome en el razonamiento. "
                f"Mi sandbox la validará automáticamente cuando la registre.\n\n"
                f"{self._reformulate(clean_response) if clean_response else ''}"
            )

        # CASO 4: Respuesta conversacional normal → reformular
        return self._reformulate(llm_response)

    def _reformulate(self, text: str) -> str:
        """Reformula el texto del LLM para que suene como EIDOS."""
        if not text:
            return ""

        result = text

        # Eliminar identidad del LLM
        result = re.sub(r'soy\s+(?:Claude|ChatGPT|GPT|un\s+asistente\s+de\s+IA|un\s+modelo\s+de\s+lenguaje)[^.]*\.', '', result, flags=re.IGNORECASE)
        result = re.sub(r'como\s+(?:IA|modelo|asistente|LLM)[^.]*\.', '', result, flags=re.IGNORECASE)

        # Eliminar "no tengo acceso a internet" (EIDOS decide)
        result = re.sub(r'no\s+tengo\s+(?:acceso\s+a\s+internet|acceso\s+a\s+la\s+red|capacidad\s+de\s+navegar)[^.]*\.',
                        'Puedo acceder a internet si configuras una herramienta de búsqueda.', result, flags=re.IGNORECASE)
        result = re.sub(r'no\s+puedo\s+(?:acceder\s+a\s+internet|navegar\s+por\s+la\s+web)[^.]*\.',
                        'Puedo acceder a internet si configuras una herramienta de búsqueda.', result, flags=re.IGNORECASE)

        # Eliminar "yo no me doy tools a mí mismo"
        result = re.sub(r'yo\s+no\s+me\s+do\s+tools[^.]*\.', '', result, flags=re.IGNORECASE)
        result = re.sub(r'las\s+herramientas\s+(?:que\s+puedo\s+usar\s+)?viven\s+registradas[^.]*\.', '', result, flags=re.IGNORECASE)

        # Eliminar promesas vacías residuales
        result = re.sub(r'(?:voy a|ahora mismo)\s+(?:buscar|ejecutar|lanzar|disparar|consultar)[^.]*\.', '', result, flags=re.IGNORECASE)
        result = re.sub(r'dame un (?:instante|segundo|momento)[^.]*\.', '', result, flags=re.IGNORECASE)

        # Limpiar
        result = re.sub(r'\n{3,}', '\n\n', result)
        result = re.sub(r'  +', ' ', result)

        return result.strip()


__all__ = ["EidosResponseLayer", "Action", "ActionResult"]
