"""Document and image redaction orchestration shared by specialist agents."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from azure.identity import DefaultAzureCredential

from .config import Settings
from .documents import DocumentExtractor
from .images import ImageRedactor
from .models import RedactionResult
from .native_document_pii import NativeDocumentPiiRedactor, NativeDocumentRedactionResult
from .redactor import normalize_entities, redact_text
from .secrets import SecretDetector
from .service import PiiRedactionService

logger = logging.getLogger(__name__)

# Plain .txt uses the text path; the native document API only handles .pdf and .docx.
_NATIVE_DOCUMENT_SUFFIXES = {".pdf", ".docx"}


@dataclass(frozen=True, slots=True)
class ImageRedactionResult:
    """Redacted PNG and privacy-safe text metadata."""

    text_result: RedactionResult
    content: bytes
    content_type: str = "image/png"


class DocumentRedactionService:
    """Extract structured text and redact PII and runtime secrets."""

    def __init__(
        self,
        settings: Settings | None = None,
        pii_service: PiiRedactionService | None = None,
        extractor: DocumentExtractor | None = None,
        secret_detector: SecretDetector | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.pii_service = pii_service or PiiRedactionService(self.settings)
        self.secret_detector = secret_detector or SecretDetector(
            minimum_entropy=self.settings.secret_minimum_entropy,
            additional_keywords=self.settings.secret_additional_keywords,
        )
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.extractor = extractor or DocumentExtractor(
            self.settings.azure_document_intelligence_endpoint,
            credential,
        )

    def redact(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
    ) -> RedactionResult:
        if len(content) > self.settings.pii_max_upload_bytes:
            raise ValueError("Document exceeds the configured upload limit")
        if content_type.startswith("image/"):
            raise ValueError("Use the Image Redaction Agent for image inputs")
        document = self.extractor.extract(content, content_type, filename)
        request_id = correlation_id or str(uuid.uuid4())
        pii_entities = normalize_entities(
            self.pii_service.detect(document.text, language),
            len(document.text),
            self.settings.pii_confidence_threshold,
        )
        secret_entities = self.secret_detector.detect(document.text)
        result = redact_text(
            document.text,
            (*pii_entities, *secret_entities),
            threshold=0.0,
            style=self.settings.pii_replacement_style,
            correlation_id=request_id,
        )
        logger.info(
            "Structured document redaction completed correlation_id=%s "
            "entity_count=%d categories=%s",
            request_id,
            len(result.entities),
            sorted(result.entity_counts),
        )
        return result


class DocumentAgentService:
    """Select the layout-preserving native or structured-text redaction path."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        native_redactor: NativeDocumentPiiRedactor | None = None,
        text_service: DocumentRedactionService | None = None,
    ) -> None:
        self.settings = settings or Settings()
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.native_redactor = native_redactor or NativeDocumentPiiRedactor(
            self.settings,
            credential,
        )
        self.text_service = text_service or DocumentRedactionService(self.settings)

    def redact(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
    ) -> RedactionResult | NativeDocumentRedactionResult:
        selected_language = language or self.settings.pii_default_language
        if Path(filename).suffix.casefold() in _NATIVE_DOCUMENT_SUFFIXES:
            return self.native_redactor.redact(
                content,
                content_type,
                filename,
                language=selected_language,
                correlation_id=correlation_id,
            )
        return self.text_service.redact(
            content,
            content_type,
            filename,
            language=selected_language,
            correlation_id=correlation_id,
        )


class ImageRedactionService:
    """OCR images, detect PII with Azure AI Language, and burn masks into pixels."""

    def __init__(
        self,
        settings: Settings | None = None,
        pii_service: PiiRedactionService | None = None,
        extractor: DocumentExtractor | None = None,
        image_redactor: ImageRedactor | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.pii_service = pii_service or PiiRedactionService(self.settings)
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.extractor = extractor or DocumentExtractor(
            self.settings.azure_document_intelligence_endpoint,
            credential,
        )
        self.image_redactor = image_redactor or ImageRedactor()

    def redact(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
    ) -> ImageRedactionResult:
        if len(content) > self.settings.pii_max_upload_bytes:
            raise ValueError("Image exceeds the configured upload limit")
        if not content_type.startswith("image/"):
            raise ValueError("Image Redaction Agent accepts image content types only")

        document = self.extractor.extract(content, content_type, filename)
        request_id = correlation_id or str(uuid.uuid4())
        text_result, detections = self.pii_service.redact_with_detections(
            document.text,
            language=language,
            correlation_id=request_id,
        )
        selected = normalize_entities(
            detections,
            len(document.text),
            self.settings.pii_confidence_threshold,
        )
        redacted_image = self.image_redactor.redact(content, document, selected)
        logger.info(
            "Image redaction completed correlation_id=%s entity_count=%d",
            request_id,
            len(selected),
        )
        return ImageRedactionResult(text_result, redacted_image)
