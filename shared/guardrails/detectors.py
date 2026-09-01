"""PII detector implementations and composition."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Protocol

from .config import CustomPattern
from .models import DetectedEntity


class PiiDetector(Protocol):
    """Contract implemented by local and Azure-backed detectors."""

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]: ...


_BUILTIN_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("Email", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"), 0.99),
    ("PhoneNumber", re.compile(r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]?)?\d{3}[ .-]\d{4}(?!\w)"), 0.88),
    ("CreditCardNumber", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"), 0.97),
    ("USTaxId", re.compile(r"(?<!\d)(?:\d{3}-\d{2}-\d{4}|\d{2}-\d{7})(?!\d)"), 0.98),
    ("IPAddress", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"), 0.90),
    ("PassportNumber", re.compile(r"(?i)passport(?: number| no| #)[: ]{1,4}(?P<value>[A-Z0-9]{6,12})"), 0.95),
    ("DriversLicenseNumber", re.compile(r"(?i)driver(?:'s)? licen[cs]e(?: number| no| #)[: ]{1,4}(?P<value>[A-Z0-9-]{4,20})"), 0.94),
    ("Person", re.compile(r"(?i)\bname[: ]{1,3}(?P<value>[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){1,3})"), 0.84),
    ("Address", re.compile(r"(?i)\baddress[: ]{1,3}(?P<value>\d{1,6}\s+[A-Za-z0-9 .'-]+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd)\b(?:[^\n,]*)(?:,\s*[A-Za-z .'-]+)?(?:,?\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?)"), 0.82),
)


def _passes_luhn(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class RegexPiiDetector:
    """Offline detector for high-signal structured PII and custom tenant patterns."""

    def __init__(self, custom_patterns: Sequence[CustomPattern] = ()) -> None:
        self._custom = tuple(
            (item.name, re.compile(item.pattern), item.replacement) for item in custom_patterns
        )

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        entities: list[DetectedEntity] = []
        for category, pattern, confidence in _BUILTIN_PATTERNS:
            for match in pattern.finditer(text):
                group = "value" if "value" in match.groupdict() else 0
                value = match.group(group)
                if category == "CreditCardNumber" and not _passes_luhn(value):
                    continue
                if category == "IPAddress" and any(int(part) > 255 for part in value.split(".")):
                    continue
                entities.append(
                    DetectedEntity(
                        category=category,
                        offset=match.start(group),
                        length=len(value),
                        confidence=confidence,
                        source="local-regex",
                        value=value,
                    )
                )
        for name, pattern, replacement in self._custom:
            for match in pattern.finditer(text):
                value = match.group(0)
                entities.append(
                    DetectedEntity(
                        category=f"Custom:{name}",
                        offset=match.start(),
                        length=len(value),
                        confidence=1.0,
                        source="custom-pattern",
                        value=value,
                        replacement=replacement,
                    )
                )
        return entities


class CompositePiiDetector:
    """Combines detector results while retaining the strongest duplicate."""

    def __init__(self, detectors: Iterable[PiiDetector]) -> None:
        self._detectors = tuple(detectors)

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        by_span: dict[tuple[int, int, str], DetectedEntity] = {}
        for detector in self._detectors:
            for entity in detector.detect(text, language):
                key = (entity.offset, entity.length, entity.category.casefold())
                previous = by_span.get(key)
                if previous is None or entity.confidence > previous.confidence:
                    by_span[key] = entity
        return list(by_span.values())
