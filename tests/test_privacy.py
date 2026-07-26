"""Tests del PrivacyFilter — Fase 2.3."""

from __future__ import annotations

import pytest

from eidos.cortex.privacy import PrivacyFilter


@pytest.fixture
def pf() -> PrivacyFilter:
    return PrivacyFilter()


class TestEmailRedaction:
    def test_email_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Contacta a juan.perez@example.com para más info")
        assert "[REDACTED_EMAIL_1]" in r.filtered_text
        assert "juan.perez@example.com" not in r.filtered_text
        assert r.redactions_count == 1
        assert r.redactions_log[0]["type"] == "EMAIL"

    def test_multiple_emails(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Envía a a@b.com y cc a x@y.org")
        assert r.redactions_count == 2
        assert "[REDACTED_EMAIL_1]" in r.filtered_text
        assert "[REDACTED_EMAIL_2]" in r.filtered_text


class TestPhoneRedaction:
    def test_spanish_phone_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Llámame al 600123456 ahora")
        assert "[REDACTED_PHONE_ES_1]" in r.filtered_text
        assert "600123456" not in r.filtered_text

    def test_international_phone_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Call +34 912345678 please")
        assert "[REDACTED_PHONE_INTL_1]" in r.filtered_text
        assert "+34 912345678" not in r.filtered_text


class TestPIIRedaction:
    def test_dni_es_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Mi DNI es 12345678Z")
        assert "[REDACTED_DNI_ES_1]" in r.filtered_text
        assert "12345678Z" not in r.filtered_text

    def test_ipv4_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("El servidor está en 192.168.1.100")
        assert "[REDACTED_IPV4_1]" in r.filtered_text
        assert "192.168.1.100" not in r.filtered_text

    def test_credit_card_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Tarjeta: 4111 1111 1111 1111")
        assert "[REDACTED_CREDIT_CARD_1]" in r.filtered_text
        assert "4111 1111 1111 1111" not in r.filtered_text

    def test_iban_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("IBAN: ES91 2100 0418 4502 0005 1332")
        assert "[REDACTED_IBAN_1]" in r.filtered_text

    def test_url_with_credentials_redacted(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Conéctate a https://admin:secret123@db.example.com")
        assert "[REDACTED_URL_CREDENTIALS_1]" in r.filtered_text
        assert "admin:secret123" not in r.filtered_text


class TestNoFalsePositives:
    def test_no_redaction_on_clean_text(self, pf: PrivacyFilter) -> None:
        r = pf.filter("Hola, ¿cómo estás? Me gusta el café.")
        assert r.redactions_count == 0
        assert r.filtered_text == "Hola, ¿cómo estás? Me gusta el café."

    def test_empty_text(self, pf: PrivacyFilter) -> None:
        r = pf.filter("")
        assert r.redactions_count == 0
        assert r.filtered_text == ""

    def test_version_numbers_not_redacted_as_ip(self, pf: PrivacyFilter) -> None:
        # "versión 1.2.3" no debe ser IP
        r = pf.filter("Estamos en la versión 1.2.3 del proyecto")
        # No debería redactar nada (1.2.3 no es IP válida)
        assert "1.2.3" in r.filtered_text


class TestMultiplePII:
    def test_multiple_types_same_text(self, pf: PrivacyFilter) -> None:
        text = "Email: juan@test.com, Tel: 600111222, IP: 10.0.0.1"
        r = pf.filter(text)
        assert r.redactions_count >= 3
        types = {item["type"] for item in r.redactions_log}
        assert "EMAIL" in types
        assert "PHONE_ES" in types
        assert "IPV4" in types

    def test_filter_str_returns_only_text(self, pf: PrivacyFilter) -> None:
        s = pf.filter_str("Email: juan@test.com")
        assert isinstance(s, str)
        assert "[REDACTED_EMAIL_1]" in s


class TestCustomPatterns:
    def test_custom_pattern_added(self) -> None:
        pf = PrivacyFilter(custom_patterns=[("CUSTOM_CODE", r"\bCOD-\d{4}\b")])
        r = pf.filter("Mi código es COD-1234")
        assert "[REDACTED_CUSTOM_CODE_1]" in r.filtered_text
