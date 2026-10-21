"""Document and image redaction orchestration shared by specialist agents."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from azure.identity import DefaultAzureCredential

from .config import Settings
from .documents import DocumentExtractor
from .images import ImageRedactor
from .models import DetectedEntity, RedactionResult
from .native_document_pii import NativeDocumentPiiRedactor, NativeDocumentRedactionResult
from .pdf_redaction import PdfSpanRedactor
from .pipeline import CustomTermDetector
from .redactor import normalize_entities, redact_text
from .secrets import SecretDetector
from .service import PiiRedactionService

logger = logging.getLogger(__name__)

# Plain .txt uses the text path; the native document API only handles .pdf and .docx.
_NATIVE_DOCUMENT_SUFFIXES = {".pdf", ".docx"}
MAX_REQUEST_CUSTOM_TERMS = 100


def parse_custom_terms(value: object) -> tuple[str, ...]:
    """Validate request-supplied custom words and phrases."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(term, str) for term in value):
        raise ValueError("custom_terms must be a list of strings")
    if len(value) > MAX_REQUEST_CUSTOM_TERMS:
        raise ValueError("custom_terms exceeds the maximum number of terms")
    terms = tuple(term for term in value if term.strip())
    CustomTermDetector(terms)  # validates term length
    return terms


def _custom_term_entities(text: str, terms: Sequence[str]) -> list[DetectedEntity]:
    return CustomTermDetector(terms).detect(text) if terms else []


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
        pdf_redactor: PdfSpanRedactor | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.pii_service = pii_service or PiiRedactionService(self.settings)
        self.pdf_redactor = pdf_redactor or PdfSpanRedactor()
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
        custom_terms: Sequence[str] = (),
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
        pii_entities.extend(_custom_term_entities(document.text, custom_terms))
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

    def redact_pdf(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
        custom_terms: Sequence[str] = (),
    ) -> NativeDocumentRedactionResult:
        """Redact PII, secrets, and custom terms from a PDF using page geometry.

        Document Intelligence locates each detected span on its page and the secure
        span redactor removes the underlying text, so values cannot be extracted.
        """
        if len(content) > self.settings.pii_max_upload_bytes:
            raise ValueError("Document exceeds the configured upload limit")
        if not content:
            raise ValueError("Document content cannot be empty")
        if content_type != "application/pdf":
            raise ValueError("Document content type does not match its filename")
        document = self.extractor.extract(content, content_type, filename)
        request_id = correlation_id or str(uuid.uuid4())
        selected = normalize_entities(
            (
                *self.pii_service.detect(document.text, language),
                *self.secret_detector.detect(document.text),
                *_custom_term_entities(document.text, custom_terms),
            ),
            len(document.text),
            self.settings.pii_confidence_threshold,
        )
        redacted = self.pdf_redactor.redact(content, document, selected)
        logger.info(
            "Structured PDF redaction completed correlation_id=%s entity_count=%d "
            "categories=%s",
            request_id,
            len(selected),
            sorted({entity.category for entity in selected}),
        )
        return NativeDocumentRedactionResult(
            content=redacted,
            content_type="application/pdf",
            filename=Path(filename).name,
            correlation_id=request_id,
        )


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
        custom_terms: Sequence[str] = (),
    ) -> RedactionResult | NativeDocumentRedactionResult:
        selected_language = language or self.settings.pii_default_language
        suffix = Path(filename).suffix.casefold()
        if custom_terms and suffix == ".pdf":
            return self.text_service.redact_pdf(
                content,
                content_type,
                filename,
                language=selected_language,
                correlation_id=correlation_id,
                custom_terms=custom_terms,
            )
        if custom_terms and suffix in _NATIVE_DOCUMENT_SUFFIXES:
            raise ValueError("Custom terms are supported for PDF and text documents only")
        if suffix in _NATIVE_DOCUMENT_SUFFIXES:
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
            custom_terms=custom_terms,
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
