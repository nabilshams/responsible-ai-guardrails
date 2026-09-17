"""Azure AI Language PII adapter using passwordless authentication."""

from __future__ import annotations

from collections.abc import Iterator

from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import TokenCredential

from .models import DetectedEntity


class AzureLanguagePiiDetector:
    """Detects contextual PII with Azure AI Language."""

    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential,
        *,
        threshold: float = 0.70,
        chunk_size: int = 5000,
    ) -> None:
        self._client = TextAnalyticsClient(endpoint=endpoint, credential=credential)
        self._threshold = threshold
        self._chunk_size = chunk_size

    def _chunks(self, text: str) -> Iterator[tuple[int, str]]:
        for offset in range(0, len(text), self._chunk_size):
            yield offset, text[offset : offset + self._chunk_size]

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []
        for base_offset, chunk in self._chunks(text):
            if not chunk:
                continue
            result = self._client.recognize_pii_entities([chunk], language=language)[0]
            if result.is_error:
                raise RuntimeError(f"Azure AI Language PII analysis failed: {result.error.code}")
            for entity in result.entities:
                confidence = float(entity.confidence_score)
                if confidence < self._threshold:
                    continue
                offset = base_offset + int(entity.offset)
                length = int(entity.length)
                entities.append(
                    DetectedEntity(
                        category=str(entity.category),
                        subcategory=str(entity.subcategory) if entity.subcategory else None,
                        offset=offset,
                        length=length,
                        confidence=confidence,
                        source="azure-ai-language",
                        value=text[offset : offset + length],
                    )
                )
        return entities
