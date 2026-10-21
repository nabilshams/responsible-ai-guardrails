import pytest

from shared.guardrails.config import Settings
from shared.guardrails.models import DetectedEntity
from shared.guardrails.pipeline import DateDetector
from shared.guardrails.service import PiiRedactionService


class StubAzureLanguageDetector:
    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        value = "synthetic.user@example.test"
        offset = text.index(value)
        return [DetectedEntity("Email", offset, len(value), 0.99, "azure-ai-language", value)]


class FixedDetector:
    def __init__(self, entities: list[DetectedEntity]) -> None:
        self.entities = entities

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del text, language
        return self.entities


def make_service() -> PiiRedactionService:
    return PiiRedactionService(
        Settings(),
        detector=StubAzureLanguageDetector(),
    )


def test_redacts_text() -> None:
    result = make_service().redact(
        "Contact synthetic.user@example.test",
        correlation_id="file-test",
    )

    assert result.redacted_text == "Contact [REDACTED:EMAIL]"


def test_requires_azure_language_endpoint_without_injected_detector() -> None:
    try:
        PiiRedactionService(Settings())
    except ValueError as exc:
        assert str(exc) == "AZURE_AI_LANGUAGE_ENDPOINT is required"
    else:
        raise AssertionError("Expected Azure AI Language endpoint validation")


def test_never_logs_detected_values(caplog) -> None:  # type: ignore[no-untyped-def]
    value = "synthetic.user@example.test"
    with caplog.at_level("INFO"):
        make_service().redact(value, correlation_id="audit-safe")

    assert value not in caplog.text
    assert "audit-safe" in caplog.text


def test_default_pipeline_is_azure_only() -> None:
    service = make_service()
    assert isinstance(service.detector, StubAzureLanguageDetector)


def test_mixed_detectors_report_sources_and_redact_once() -> None:
    settings = Settings(
        pii_custom_terms=["Project Falcon"],
        pii_enable_secret_detection=True,
    )
    service = PiiRedactionService(settings, detector=StubAzureLanguageDetector())
    text = (
        "Project Falcon: synthetic.user@example.test "
        "api_key=Qx7mP2vLw9Zt4RbN"
    )

    result = service.redact(text, correlation_id="mixed")

    assert {entity.source for entity in result.entities} == {
        "azure-ai-language",
        "custom-terms",
        "deterministic-secret-detector",
    }
    assert result.redacted_text.count("[REDACTED:EMAIL]") == 1
    assert "synthetic.user" not in result.redacted_text
    assert "Qx7mP2vLw9Zt4RbN" not in result.redacted_text
    assert "Falcon" not in result.redacted_text


def test_custom_terms_without_azure() -> None:
    service = PiiRedactionService(
        Settings(pii_enable_azure_language=False, pii_custom_terms=["Contoso Secret"]),
    )

    result = service.redact("a contoso secret b", correlation_id="custom")

    assert result.redacted_text == "a [REDACTED:CUSTOMTERM] b"


def test_requires_at_least_one_detector() -> None:
    try:
        PiiRedactionService(Settings(pii_enable_azure_language=False))
    except ValueError as exc:
        assert "detector" in str(exc)
    else:
        raise AssertionError("Expected detector validation")


def test_overlap_resolution_is_order_independent() -> None:
    from shared.guardrails.redactor import normalize_entities

    a = DetectedEntity("A", 0, 5, 0.9, "s1", "abcde")
    b = DetectedEntity("B", 0, 5, 0.9, "s2", "abcde")
    assert normalize_entities([a, b], 5, 0.0) == normalize_entities([b, a], 5, 0.0) == [a]


@pytest.mark.parametrize(
    "date_text",
    ["2026-01-10", "10/01/2026", "10 January 2026", "January 10, 2026", "10 Jan 2026"],
)
def test_date_detector_redacts_complete_date(date_text: str) -> None:
    service = PiiRedactionService(
        Settings(pii_enable_azure_language=False, pii_enable_date_detection=True),
    )
    text = f"Born on {date_text}, per the file."
    result = service.redact(text, correlation_id="date")
    assert result.redacted_text == "Born on [REDACTED:DATETIME], per the file."
    assert [(e.source, e.length) for e in result.entities] == [
        ("deterministic-date-detector", len(date_text))
    ]


def test_date_detector_replaces_partial_azure_span() -> None:
    text = "Visit on 10 January 2026."
    partial = DetectedEntity("DateTime", 9, 7, 0.9, "azure-ai-language", "10 Janu")
    service = PiiRedactionService(
        Settings(pii_enable_date_detection=True), detector=FixedDetector([partial])
    )
    result = service.redact(text, correlation_id="partial")
    assert result.redacted_text == "Visit on [REDACTED:DATETIME]."


@pytest.mark.parametrize(
    "text",
    [
        "Order 12345678 shipped",
        "Version 1.2.3 and 10.5.2",
        "Call 555-12-3456",
        "I may 5 times, in March we rest, 10 Jan",
        "Total 31/02/2026 is invalid",
        "Range 2026-13-45",
        "Part 110/01/2026",
    ],
)
def test_date_detector_ignores_non_dates(text: str) -> None:
    assert DateDetector().detect(text) == []


MEDICARE_SOURCE = "deterministic-medicare-detector"


def medicare_service(azure: list[DetectedEntity] | None = None) -> PiiRedactionService:
    return PiiRedactionService(
        Settings(pii_enable_azure_language=azure is not None, pii_enable_medicare_detection=True),
        detector=FixedDetector(azure) if azure is not None else None,
    )


@pytest.mark.parametrize(
    "number",
    ["2123456701", "2123 45670 1", "2123-45670-1", "2123 45670 1/2", "2123 45670 1 / 2"],
)
def test_medicare_detects_valid_variants(number: str) -> None:
    result = medicare_service().redact(f"Card {number}, thanks.", correlation_id="m")
    assert result.redacted_text == "Card [REDACTED:AUMEDICARENUMBER], thanks."
    assert [(e.category, e.source, e.length) for e in result.entities] == [
        ("AUMedicareNumber", MEDICARE_SOURCE, len(number))
    ]


def test_medicare_overrides_azure_phone_classification() -> None:
    text = "Medicare 2123 45670 1 on file"
    value = "2123 45670 1"
    phone = DetectedEntity("PhoneNumber", 9, len(value), 1.0, "azure-ai-language", value)
    result = medicare_service([phone]).redact(text, correlation_id="m")
    assert result.redacted_text == "Medicare [REDACTED:AUMEDICARENUMBER] on file"
    assert [e.source for e in result.entities] == [MEDICARE_SOURCE]


def test_medicare_keeps_unrelated_azure_entities() -> None:
    text = "Call 0412 345 678 re 2123456701"
    phone = DetectedEntity("PhoneNumber", 5, 12, 0.95, "azure-ai-language", "0412 345 678")
    result = medicare_service([phone]).redact(text, correlation_id="m")
    assert result.redacted_text == "Call [REDACTED:PHONENUMBER] re [REDACTED:AUMEDICARENUMBER]"


@pytest.mark.parametrize(
    "text",
    [
        "Card 2123456711",  # bad check digit
        "Card 1123456701",  # invalid leading digit
        "Card 2123456700",  # issue number 0
        "Call 0412345678",
        "Call 02 1234 5670",
        "Account 12123456701",
        "Account 21234567012",
        "Ref 2123-4567-01-9",
        "Version 2.1234567.01",
    ],
)
def test_medicare_ignores_lookalikes(text: str) -> None:
    from shared.guardrails.pipeline import MedicareDetector

    assert MedicareDetector().detect(text) == []
