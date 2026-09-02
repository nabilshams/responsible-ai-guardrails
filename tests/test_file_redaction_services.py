from io import BytesIO

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
    ("filename", "content_type"),
    [
        ("synthetic.txt", "text/plain"),
        ("synthetic.csv", "text/csv"),
        ("synthetic.json", "application/json"),
        ("synthetic.xml", "application/xml"),
        ("synthetic.md", "text/markdown"),
        ("synthetic.log", "application/octet-stream"),
    ],
)
def test_document_agent_extracts_and_redacts_supported_utf8_files(
    filename: str,
    content_type: str,
) -> None:
    service = DocumentRedactionService(
        Settings(),
        pii_service=pii_service(),
        extractor=DocumentExtractor(),
    )

    result = service.redact(
        b"Contact synthetic.user@example.test",
        content_type,
        filename,
        correlation_id="synthetic-document",
    )

    assert result.redacted_text == "Contact [REDACTED:EMAIL]"
    assert result.correlation_id == "synthetic-document"


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
