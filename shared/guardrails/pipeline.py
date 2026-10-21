"""Composable PII detection pipeline: Azure AI Language, custom terms, and secrets."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import date

from .detectors import PiiDetector
from .models import DetectedEntity
from .secrets import SecretDetector

CUSTOM_TERM_SOURCE = "custom-terms"
CUSTOM_TERM_CATEGORY = "CustomTerm"
MAX_CUSTOM_TERM_LENGTH = 256
DATE_SOURCE = "deterministic-date-detector"
DATE_CATEGORY = "DateTime"
DATE_SUBCATEGORY = "Date"
MEDICARE_SOURCE = "deterministic-medicare-detector"
MEDICARE_CATEGORY = "AUMedicareNumber"
_PHONE_CATEGORIES = frozenset({"phonenumber", "phone"})

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}  # fmt: skip
_MONTH = r"(?P<month>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_YEAR = r"(?P<year>(?:19|20)\d{2})"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_BOUND_START = r"(?<![\w.\-/])"
_BOUND_END = r"(?![\w\-/]|[.,]\d)"
_DATE_PATTERNS = (
    # 2026-01-10, 2026/01/10, 2026.01.10
    re.compile(
        _BOUND_START
        + r"(?P<year>(?:19|20)\d{2})(?P<sep>[-/.])(?P<a>\d{1,2})(?P=sep)(?P<b>\d{1,2})"
        + _BOUND_END
    ),
    # 10/01/2026, 10-01-2026, 10.01.2026 (day and month order are both accepted)
    re.compile(
        _BOUND_START + r"(?P<a>\d{1,2})(?P<sep>[-/.])(?P<b>\d{1,2})(?P=sep)" + _YEAR + _BOUND_END
    ),
    # 10 January 2026, 10th Jan, 2026
    re.compile(
        _BOUND_START
        + _DAY
        + r"[ \t]+(?:of[ \t]+)?"
        + _MONTH
        + r"[ \t]*,?[ \t]*"
        + _YEAR
        + _BOUND_END,
        re.IGNORECASE,
    ),
    # January 10, 2026 / Jan. 10th 2026
    re.compile(
        _BOUND_START + _MONTH + r"[ \t]+" + _DAY + r"[ \t]*,?[ \t]*" + _YEAR + _BOUND_END,
        re.IGNORECASE,
    ),
)


def _is_valid_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


class DateDetector:
    """Detect complete calendar dates in explicit numeric and month-name formats.

    Month-name dates require a four-digit year, and numeric dates require a
    separator-delimited year, so bare numbers and phrases such as "may 5" are ignored.
    Impossible calendar dates are rejected.
    """

    def __init__(self, *, category: str = DATE_CATEGORY) -> None:
        self.category = category

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        found: dict[tuple[int, int], DetectedEntity] = {}
        for pattern in _DATE_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groupdict()
                year = int(groups["year"])
                if "month" in groups:
                    month_day = [(_MONTHS[groups["month"].lower()], int(groups["day"]))]
                else:
                    first, second = int(groups["a"]), int(groups["b"])
                    if match.start("year") < match.start("a"):
                        month_day = [(first, second)]
                    else:
                        month_day = [(first, second), (second, first)]
                if not any(_is_valid_date(year, m, d) for m, d in month_day):
                    continue
                span = (match.start(), match.end())
                found.setdefault(
                    span,
                    DetectedEntity(
                        category=self.category,
                        subcategory=DATE_SUBCATEGORY,
                        offset=span[0],
                        length=span[1] - span[0],
                        confidence=1.0,
                        source=DATE_SOURCE,
                        value=match.group(0),
                    ),
                )
        return sorted(found.values(), key=lambda item: item.offset)


_MEDICARE_PATTERN = re.compile(
    r"(?<![\w.\-/])(?P<card>[2-6]\d{3}[ -]?\d{5}[ -]?\d)(?P<irn>[ ]?/[ ]?\d)?(?![\w\-]|[./]\d)"
)
_MEDICARE_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9)


def is_valid_medicare_number(digits: str) -> bool:
    """Validate a 10-digit Medicare card number: first digit 2-6, check digit, issue 1-9."""
    if len(digits) != 10 or not digits.isdigit() or digits[0] not in "23456" or digits[9] == "0":
        return False
    total = sum(int(d) * w for d, w in zip(digits[:8], _MEDICARE_WEIGHTS, strict=True))
    return total % 10 == int(digits[8])


class MedicareDetector:
    """Detect checksum-valid Australian Medicare card numbers.

    Accepts 10 digits with optional space or hyphen separators (4-5-1 grouping) and an
    optional ``/n`` individual reference number. Invalid check digits are ignored.
    """

    def __init__(self, *, category: str = MEDICARE_CATEGORY) -> None:
        self.category = category

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        entities: list[DetectedEntity] = []
        for match in _MEDICARE_PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group("card"))
            if not is_valid_medicare_number(digits):
                continue
            entities.append(
                DetectedEntity(
                    category=self.category,
                    offset=match.start(),
                    length=match.end() - match.start(),
                    confidence=1.0,
                    source=MEDICARE_SOURCE,
                    value=match.group(0),
                )
            )
        return entities


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
        medicare = [entity for entity in entities if entity.source == MEDICARE_SOURCE]
        if not medicare:
            return entities
        return [
            entity
            for entity in entities
            if entity.source == MEDICARE_SOURCE
            or entity.category.lower() not in _PHONE_CATEGORIES
            or not any(entity.offset < m.end and m.offset < entity.end for m in medicare)
        ]
