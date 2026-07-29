"""Tests del EIDOS Response Layer — EIDOS habla como EIDOS."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from eidos.core.monologue import Monologue
from eidos.core.response_layer import EidosResponseLayer, Action, ActionResult


@pytest.fixture
def mock_monologue() -> Monologue:
    return Monologue(
        input_summary="test",
        observation="obs",
        hypothesis="hyp",
        plan=["step1"],
        risk="none",
        confidence=0.85,
        response="Hola, soy Claude...",
        backend="api",
    )


@pytest.fixture
def mock_sandbox() -> MagicMock:
    sandbox = MagicMock()
    result = MagicMock()
    result.is_security_error = False
    result.security_violations = []
    result.ok = True
    result.exit_code = 0
    result.stderr = ""
    sandbox.run_code.return_value = result
    sandbox.smoke_test_tool.return_value = result
    return sandbox


@pytest.fixture
def response_layer(mock_sandbox: MagicMock) -> EidosResponseLayer:
    return EidosResponseLayer(sandbox=mock_sandbox, memory=None)


class TestEidosResponseLayer:
    def test_eidos_speaks_in_first_person(
        self, response_layer: EidosResponseLayer, mock_monologue: Monologue
    ) -> None:
        """EIDOS debe responder como EIDOS, no como el LLM."""
        response = response_layer.process(
            llm_response="Hola, soy Claude. ¿En qué puedo ayudarte?",
            monologue=mock_monologue,
            context={},
        )
        assert "Claude" not in response
        assert "soy un asistente" not in response.lower()

    def test_eidos_executes_actions_before_responding(
        self, response_layer: EidosResponseLayer, mock_monologue: Monologue
    ) -> None:
        """Si el LLM genera código, EIDOS debe validarlo antes de responder."""
        response = response_layer.process(
            llm_response="Aquí tienes el código:\n```python\ndef imc(peso, altura):\n    return peso / altura**2\n```",
            monologue=mock_monologue,
            context={},
        )
        assert "validado" in response.lower() or "sandbox" in response.lower()
        assert "```python" not in response

    def test_code_rejection_reported(
        self, mock_monologue: Monologue
    ) -> None:
        """Si el sandbox rechaza el código, EIDOS informa del error."""
        sandbox = MagicMock()
        result = MagicMock()
        result.is_security_error = True
        result.security_violations = ["Import 'os' not in whitelist"]
        result.ok = False
        result.exit_code = -1
        result.stderr = "error"
        sandbox.run_code.return_value = result
        sandbox.smoke_test_tool.return_value = result

        layer = EidosResponseLayer(sandbox=sandbox, memory=None)
        response = layer.process(
            llm_response="```python\nimport os\nos.system('rm -rf /')\n```",
            monologue=mock_monologue,
            context={},
        )
        assert "rechazado" in response.lower() or "seguridad" in response.lower()

    def test_no_code_passes_through_reformulated(
        self, response_layer: EidosResponseLayer, mock_monologue: Monologue
    ) -> None:
        """Respuestas sin código pasan pero reformuladas."""
        response = response_layer.process(
            llm_response="El libre albedrío es un concepto filosófico fascinante.",
            monologue=mock_monologue,
            context={},
        )
        assert "libre albedrío" in response.lower()

    def test_llm_identity_removed(
        self, response_layer: EidosResponseLayer, mock_monologue: Monologue
    ) -> None:
        """Referencias a Claude/GPT/ChatGPT deben eliminarse."""
        response = response_layer.process(
            llm_response="Soy Claude, un modelo de Anthropic. Te ayudo con eso.",
            monologue=mock_monologue,
            context={},
        )
        assert "Claude" not in response
        assert "Anthropic" not in response
        assert "modelo de" not in response.lower()

    def test_internet_access_claims_replaced(
        self, response_layer: EidosResponseLayer, mock_monologue: Monologue
    ) -> None:
        """El LLM no debe decir 'no tengo acceso a internet'."""
        response = response_layer.process(
            llm_response="No tengo acceso a internet en tiempo real.",
            monologue=mock_monologue,
            context={},
        )
        assert "no tengo acceso a internet" not in response.lower()
