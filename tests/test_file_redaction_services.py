import csv
import json
import logging
from io import BytesIO, StringIO
from xml.etree import ElementTree

import pytest
from PIL import Image

from shared.guardrails.config import Settings
from shared.guardrails.documents import DocumentExtractor
from shared.guardrails.file_services import DocumentRedactionService, ImageRedactionService
from shared.guardrails.models import DetectedEntity, ExtractedDocument, TextRegion
from shared.guardrails.service import PiiRedactionService


class StubAzureLanguageDetector:
    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        value = "synthetic.user@example.test"
        if value not in text:
            return []
        return [
            DetectedEntity(
                "Email",
                text.index(value),
                len(value),
                0.99,
                "azure-ai-language",
                value,
            )
        ]


class StubOverlappingPiiDetector:
    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        value = "synthetic_client_secret_Q7v9X2m4"
        return [
            DetectedEntity(
                "Organization",
                text.index(value),
                len(value),
                0.75,
                "azure-ai-language",
                value,
            )
        ]


class StubImageExtractor:
    def extract(self, content: bytes, content_type: str, filename: str) -> ExtractedDocument:
        del content, content_type, filename
        value = "synthetic.user@example.test"
        return ExtractedDocument(
            text=value,
            regions=(TextRegion(0, len(value), (10, 10, 70, 10, 70, 30, 10, 30)),),
            page_width=100,
            page_height=50,
        )


def pii_service() -> PiiRedactionService:
    return PiiRedactionService(Settings(), detector=StubAzureLanguageDetector())


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        (
            "synthetic.txt",
            "text/plain",
            "Contact synthetic.user@example.test\n"
            "client_secret=synthetic_client_secret_Q7v9X2m4",
        ),
        (
            "synthetic.csv",
            "text/csv",
            "email,configuration\nsynthetic.user@example.test,"
            "client_secret=synthetic_client_secret_Q7v9X2m4\n",
        ),
        (
            "synthetic.json",
            "application/json",
            '{"email":"synthetic.user@example.test","client_secret":'
            '"synthetic_client_secret_Q7v9X2m4"}',
        ),
        (
            "synthetic.xml",
            "application/xml",
            "<record><email>synthetic.user@example.test</email>"
            '<credential client_secret="synthetic_client_secret_Q7v9X2m4" />'
            "</record>",
        ),
        (
            "synthetic.md",
            "text/markdown",
            "Email: synthetic.user@example.test\n"
            "client_secret=synthetic_client_secret_Q7v9X2m4\n",
        ),
        (
            "synthetic.log",
            "application/octet-stream",
            "email=synthetic.user@example.test "
            "client_secret=synthetic_client_secret_Q7v9X2m4\n",
        ),
    ],
)
def test_document_agent_redacts_pii_and_secrets_in_supported_utf8_files(
    filename: str,
    content_type: str,
    content: str,
) -> None:
    service = DocumentRedactionService(
        Settings(),
        pii_service=pii_service(),
        extractor=DocumentExtractor(),
    )

    result = service.redact(
        content.encode(),
        content_type,
        filename,
        correlation_id="synthetic-document",
    )

    assert "synthetic.user@example.test" not in result.redacted_text
    assert "synthetic_client_secret_Q7v9X2m4" not in result.redacted_text
    assert "[REDACTED:EMAIL]" in result.redacted_text
    assert "[REDACTED:GENERICSECRET]" in result.redacted_text
    assert result.entity_counts == {"Email": 1, "GenericSecret": 1}
    assert result.correlation_id == "synthetic-document"
    if filename.endswith(".csv"):
        assert len(list(csv.reader(StringIO(result.redacted_text)))) == 2
    elif filename.endswith(".json"):
        assert "[REDACTED:GENERICSECRET]" in json.loads(
            result.redacted_text
        ).values()
    elif filename.endswith(".xml"):
        assert ElementTree.fromstring(  # noqa: S314 - bounded synthetic fixture.
            result.redacted_text
        ).tag == "record"


def test_document_agent_prefers_secret_category_for_overlapping_detection() -> None:
    service = DocumentRedactionService(
        Settings(),
        pii_service=PiiRedactionService(
            Settings(),
            detector=StubOverlappingPiiDetector(),
        ),
        extractor=DocumentExtractor(),
    )

    result = service.redact(
        b"client_secret=synthetic_client_secret_Q7v9X2m4",
        "text/plain",
        "synthetic.txt",
        correlation_id="synthetic-overlap",
    )

    assert result.redacted_text == "client_secret=[REDACTED:GENERICSECRET]"
    assert result.entity_counts == {"GenericSecret": 1}


def test_document_agent_logs_only_safe_combined_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    credential = "synthetic_client_secret_Q7v9X2m4"
    service = DocumentRedactionService(
        Settings(),
        pii_service=pii_service(),
        extractor=DocumentExtractor(),
    )

    with caplog.at_level(logging.INFO):
        service.redact(
            f"client_secret={credential}".encode(),
            "text/plain",
            "synthetic.txt",
            correlation_id="synthetic-log",
        )

    assert credential not in caplog.text
    assert "GenericSecret" in caplog.text


def test_document_agent_rejects_image_inputs() -> None:
    service = DocumentRedactionService(
        Settings(),
        pii_service=pii_service(),
        extractor=DocumentExtractor(),
    )

    with pytest.raises(ValueError, match="Image Redaction Agent"):
        service.redact(b"synthetic", "image/png", "synthetic.png")


def test_image_agent_burns_mask_over_detected_pii() -> None:
    source = Image.new("RGB", (100, 50), "white")
    buffer = BytesIO()
    source.save(buffer, format="PNG")
    service = ImageRedactionService(
        Settings(),
        pii_service=pii_service(),
        extractor=StubImageExtractor(),
    )

    result = service.redact(
        buffer.getvalue(),
        "image/png",
        "synthetic.png",
        correlation_id="synthetic-image",
    )

    assert result.text_result.redacted_text == "[REDACTED:EMAIL]"
    assert result.content_type == "image/png"
    with Image.open(BytesIO(result.content)) as redacted:
        assert redacted.getpixel((20, 20)) == (0, 0, 0)
        assert redacted.getpixel((90, 40)) == (255, 255, 255)


def test_image_agent_rejects_non_image_inputs() -> None:
    service = ImageRedactionService(
        Settings(),
        pii_service=pii_service(),
        extractor=StubImageExtractor(),
    )

    with pytest.raises(ValueError, match="image content types only"):
        service.redact(b"synthetic", "application/pdf", "synthetic.pdf")
