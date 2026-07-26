"""PrivacyFilter — Fase 2.3.

Redacta PII (Personally Identifiable Information) antes de enviar
cualquier texto a una API externa. EIDOS es privado por diseño;
el fallback a APIs externas es opt-in y SIEMPRE pasa por este filtro.

Reglas soportadas (regex):
- Emails
- Teléfonos (ES e internacional, con/sin prefijo +)
- IPs IPv4
- DNIs españoles (8 dígitos + letra)
- Tarjetas de crédito (grupos de 4 dígitos)
- IBAN (ES + 22 caracteres)
- URLs con credenciales embebidas (user:pass@)

Cada match se reemplaza por un token tipo [REDACTED_EMAIL_1].
El filtro devuelve (filtered_text, redactions_count, redactions_log).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from eidos.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Patrones PII
# ---------------------------------------------------------------------------

# Orden importa: patrones más específicos primero.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # URL con credenciales: scheme://user:pass@host — PRIMERO, antes que email
    ("URL_CREDENTIALS", re.compile(r"\bhttps?://[^/\s:@]+:[^/\s:@]+@[^\s]+")),
    # IBAN español: ES + 22 dígitos en grupos de 1-4, separados por espacio opcional
    ("IBAN", re.compile(r"\bES\d{2}(?:[ ]?\d{4}){5}\b")),
    # Tarjeta de crédito (4 grupos de 4 dígitos, separadores espacio o -)
    ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    # Email
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    # DNI español: 8 dígitos + letra (mayúscula o minúscula)
    ("DNI_ES", re.compile(r"\b\d{8}[A-Za-z]\b")),
    # IP IPv4
    ("IPV4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    # Teléfono internacional con prefijo + y 7-15 dígitos
    ("PHONE_INTL", re.compile(r"\+\d{1,3}[\s-]?\d{6,14}\b")),
    # Teléfono español: 9 dígitos consecutivos empezando por 6/7/9
    ("PHONE_ES", re.compile(r"\b[679]\d{8}\b")),
]


@dataclass
class FilterResult:
    """Resultado de aplicar PrivacyFilter."""

    filtered_text: str
    redactions_count: int = 0
    redactions_log: list[dict[str, Any]] = field(default_factory=list)
    # metadata adicional para auditoría
    original_length: int = 0
    filtered_length: int = 0


class PrivacyFilter:
    """Redacta PII antes de llamadas a APIs externas.

    Uso:
        pf = PrivacyFilter()
        result = pf.filter("Contacta a juan@example.com al 600123456")
        # result.filtered_text == "Contacta a [REDACTED_EMAIL_1] al [REDACTED_PHONE_ES_1]"
        # result.redactions_count == 2
    """

    def __init__(self, custom_patterns: list[tuple[str, str]] | None = None) -> None:
        self._patterns = list(_PATTERNS)
        if custom_patterns:
            for name, pat in custom_patterns:
                self._patterns.append((name, re.compile(pat)))

    def filter(self, text: str) -> FilterResult:
        """Aplica todas las reglas y devuelve el texto redactado + log."""
        if not text:
            return FilterResult(filtered_text="", original_length=0, filtered_length=0)

        original_length = len(text)
        filtered = text
        redactions_log: list[dict[str, Any]] = []
        counters: dict[str, int] = {}

        for pii_type, pattern in self._patterns:
            matches = list(pattern.finditer(filtered))
            if not matches:
                continue
            # Reemplazar de derecha a izquierda para no romper offsets
            for m in reversed(matches):
                counters[pii_type] = counters.get(pii_type, 0) + 1
                idx = counters[pii_type]
                token = f"[REDACTED_{pii_type}_{idx}]"
                redactions_log.append(
                    {
                        "type": pii_type,
                        "token": token,
                        "start": m.start(),
                        "end": m.end(),
                        # NO guardamos el valor original por seguridad
                        "length": m.end() - m.start(),
                    }
                )
                filtered = filtered[: m.start()] + token + filtered[m.end() :]

        result = FilterResult(
            filtered_text=filtered,
            redactions_count=len(redactions_log),
            redactions_log=redactions_log,
            original_length=original_length,
            filtered_length=len(filtered),
        )
        if redactions_log:
            logger.info(
                "privacy_filtered",
                redactions=len(redactions_log),
                types=list({r["type"] for r in redactions_log}),
            )
        return result

    def filter_str(self, text: str) -> str:
        """Conveniencia: devuelve solo el texto filtrado (sin log)."""
        return self.filter(text).filtered_text


__all__ = ["PrivacyFilter", "FilterResult"]
