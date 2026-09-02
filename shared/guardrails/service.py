"""Orchestration service used by APIs, agents, and evaluations."""

from __future__ import annotations

import logging
import uuid

from azure.identity import DefaultAzureCredential

from .azure_language import AzureLanguagePiiDetector
from .config import Settings
from .detectors import PiiDetector
from .models import DetectedEntity, RedactionResult
from .redactor import redact_text

logger = logging.getLogger(__name__)


class PiiRedactionService:
    """Coordinates Azure AI Language detection and deterministic text redaction."""

    def __init__(
        self,
        settings: Settings | None = None,
        detector: PiiDetector | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.detector = detector or self._build_detector()

    def _build_detector(self) -> PiiDetector:
        endpoint = self.settings.azure_ai_language_endpoint
        if not endpoint:
            raise ValueError("AZURE_AI_LANGUAGE_ENDPOINT is required")
        return AzureLanguagePiiDetector(
            endpoint,
            DefaultAzureCredential(exclude_interactive_browser_credential=True),
            threshold=self.settings.pii_confidence_threshold,
        )

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
        result, _ = self.redact_with_detections(
            text,
            language=language,
            correlation_id=correlation_id,
        )
        return result

    def redact_with_detections(
        self,
        text: str,
        *,
        language: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[RedactionResult, list[DetectedEntity]]:
        """Redact text and return internal detections for geometry-aware transforms."""
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
        return result, entities
