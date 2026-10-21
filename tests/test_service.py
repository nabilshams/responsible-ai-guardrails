from shared.guardrails.config import Settings
from shared.guardrails.models import DetectedEntity
from shared.guardrails.service import PiiRedactionService


class StubAzureLanguageDetector:
    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        value = "synthetic.user@example.test"
        offset = text.index(value)
        return [DetectedEntity("Email", offset, len(value), 0.99, "azure-ai-language", value)]


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
