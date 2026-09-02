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
