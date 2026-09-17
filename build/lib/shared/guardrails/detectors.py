"""PII detector contract used by the Azure AI Language adapter."""

from __future__ import annotations

from typing import Protocol

from .models import DetectedEntity


class PiiDetector(Protocol):
    """Contract implemented by Azure AI Language and deterministic test doubles."""

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]: ...
