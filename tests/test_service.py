from shared.guardrails.config import Settings
from shared.guardrails.detectors import RegexPiiDetector
from shared.guardrails.documents import DocumentExtractor, UnsupportedDocumentError
from shared.guardrails.service import PiiRedactionService


def make_service() -> PiiRedactionService:
    return PiiRedactionService(
        Settings(pii_backend="local"),
        detector=RegexPiiDetector(),
        extractor=DocumentExtractor(),
    )


def test_redacts_utf8_text_document() -> None:
    result = make_service().redact_file(
        b"Contact synthetic.user@example.test",
        "text/plain",
        "sample.txt",
        correlation_id="file-test",
    )

    assert result.content is None
    assert result.text_result.redacted_text == "Contact [REDACTED:EMAIL]"


def test_rejects_unsupported_binary_without_azure() -> None:
    service = make_service()
    try:
        service.redact_file(b"binary", "application/pdf", "sample.pdf")
    except UnsupportedDocumentError as exc:
        assert "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT" in str(exc)
    else:
        raise AssertionError("Expected UnsupportedDocumentError")


def test_never_logs_detected_values(caplog) -> None:  # type: ignore[no-untyped-def]
    value = "synthetic.user@example.test"
    with caplog.at_level("INFO"):
        make_service().redact(value, correlation_id="audit-safe")

    assert value not in caplog.text
    assert "audit-safe" in caplog.text
