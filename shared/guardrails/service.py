"""Orchestration service used by APIs, agents, and evaluations."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from azure.identity import DefaultAzureCredential

from .azure_language import AzureLanguagePiiDetector
from .config import Settings
from .detectors import CompositePiiDetector, PiiDetector, RegexPiiDetector
from .documents import DocumentExtractor
from .images import ImageRedactor
from .models import DetectedEntity, RedactionResult
from .redactor import normalize_entities, redact_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FileRedactionResult:
    """Redacted file result with safe metadata."""

    text_result: RedactionResult
    content: bytes | None = None
    content_type: str | None = None


class PiiRedactionService:
    """Coordinates detection, redaction, and optional Azure document extraction."""

    def __init__(
        self,
        settings: Settings | None = None,
        detector: PiiDetector | None = None,
        extractor: DocumentExtractor | None = None,
    ) -> None:
        self.settings = settings or Settings()
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.detector = detector or self._build_detector(credential)
        self.extractor = extractor or DocumentExtractor(
            self.settings.azure_document_intelligence_endpoint,
            credential,
        )
        self.image_redactor = ImageRedactor()

    def _build_detector(self, credential: DefaultAzureCredential) -> PiiDetector:
        local = RegexPiiDetector(self.settings.pii_custom_patterns)
        if self.settings.pii_backend == "local":
            return local
        endpoint = self.settings.azure_ai_language_endpoint
        if not endpoint:
            raise ValueError(
                "AZURE_AI_LANGUAGE_ENDPOINT is required when PII_BACKEND is azure or hybrid"
            )
        azure = AzureLanguagePiiDetector(
            endpoint,
            credential,
            threshold=self.settings.pii_confidence_threshold,
        )
        return azure if self.settings.pii_backend == "azure" else CompositePiiDetector([azure, local])

    def detect(self, text: str, language: str | None = None) -> list[DetectedEntity]:
        """Detect sensitive spans. Callers must not log the returned values."""
        return self.detector.detect(text, language or self.settings.pii_default_language)

    def redact(
        self,
        text: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
    ) -> RedactionResult:
        request_id = correlation_id or str(uuid.uuid4())
        entities = self.detect(text, language)
        result = redact_text(
            text,
            entities,
            threshold=self.settings.pii_confidence_threshold,
            style=self.settings.pii_replacement_style,
            correlation_id=request_id,
        )
        logger.info(
            "PII redaction completed correlation_id=%s entity_count=%d categories=%s",
            request_id,
            len(result.entities),
            sorted(result.entity_counts),
        )
        return result

    def redact_file(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
    ) -> FileRedactionResult:
        if len(content) > self.settings.pii_max_upload_bytes:
            raise ValueError("File exceeds the configured upload limit")
        document = self.extractor.extract(content, content_type, filename)
        request_id = correlation_id or str(uuid.uuid4())
        raw_entities = self.detect(document.text, language)
        selected = normalize_entities(
            raw_entities,
            len(document.text),
            self.settings.pii_confidence_threshold,
        )
        text_result = redact_text(
            document.text,
            selected,
            threshold=self.settings.pii_confidence_threshold,
            style=self.settings.pii_replacement_style,
            correlation_id=request_id,
        )
        if content_type.startswith("image/"):
            redacted_image = self.image_redactor.redact(content, document, selected)
            return FileRedactionResult(text_result, redacted_image, "image/png")
        return FileRedactionResult(text_result)
