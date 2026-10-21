"""Composable PII detection pipeline: Azure AI Language, custom terms, and secrets."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .detectors import PiiDetector
from .models import DetectedEntity
from .secrets import SecretDetector

CUSTOM_TERM_SOURCE = "custom-terms"
CUSTOM_TERM_CATEGORY = "CustomTerm"
MAX_CUSTOM_TERM_LENGTH = 256


class CustomTermDetector:
    """Match user-supplied words or phrases case-insensitively on token boundaries."""

    def __init__(self, terms: Iterable[str], *, category: str = CUSTOM_TERM_CATEGORY) -> None:
        cleaned = {term.strip() for term in terms if term and term.strip()}
        if any(len(term) > MAX_CUSTOM_TERM_LENGTH for term in cleaned):
            raise ValueError("Custom terms must not exceed the maximum length")
        self.category = category
        ordered = sorted(cleaned, key=lambda term: (-len(term), term.casefold()))
        self._pattern = (
            re.compile(
                r"(?<!\w)(?:" + "|".join(re.escape(term) for term in ordered) + r")(?!\w)",
                re.IGNORECASE,
            )
            if ordered
            else None
        )

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        if self._pattern is None:
            return []
        return [
            DetectedEntity(
                category=self.category,
                offset=match.start(),
                length=match.end() - match.start(),
                confidence=1.0,
                source=CUSTOM_TERM_SOURCE,
                value=match.group(0),
            )
            for match in self._pattern.finditer(text)
        ]


class SecretPiiDetector:
    """Adapt the deterministic secret detector to the ``PiiDetector`` contract."""

    def __init__(self, detector: SecretDetector | None = None) -> None:
        self._detector = detector or SecretDetector()

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        return self._detector.detect(text)


class CompositePiiDetector:
    """Run every enabled detector over the same text and return all source-tagged spans.

    Overlap and duplicate resolution is left to ``normalize_entities`` so spans are
    redacted exactly once, deterministically.
    """

    def __init__(self, detectors: Sequence[PiiDetector]) -> None:
        self.detectors = tuple(detectors)

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []
        for detector in self.detectors:
            entities.extend(detector.detect(text, language))
        return entities
