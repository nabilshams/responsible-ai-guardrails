"""Regex-based PII pattern definitions used by detection/redaction guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re


@dataclass(frozen=True)
class PIIPattern:
    label: str
    pattern: re.Pattern[str]
    placeholder: str


def _compile(label: str, raw_pattern: str, placeholder: str, ignore_case: bool = True) -> PIIPattern:
    flags = re.IGNORECASE if ignore_case else 0
    return PIIPattern(label=label, pattern=re.compile(raw_pattern, flags), placeholder=placeholder)


DEFAULT_PII_PATTERNS: tuple[PIIPattern, ...] = (
    _compile("EMAIL", r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED:EMAIL]"),
    _compile("PHONE", r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b", "[REDACTED:PHONE]"),
    _compile("CREDIT_CARD", r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED:CREDIT_CARD]"),
    _compile("TAX_ID", r"\b(?:\d{3}-\d{2}-\d{4}|\d{2}-\d{7})\b", "[REDACTED:TAX_ID]"),
    _compile("DRIVER_LICENSE", r"\b[A-Z]{2}\d{6,8}\b", "[REDACTED:DRIVER_LICENSE]"),
    _compile("PASSPORT", r"\b[A-Z]\d{8}\b", "[REDACTED:PASSPORT]"),
    _compile(
        "ADDRESS",
        r"\b\d{1,6}\s+[A-Za-z0-9.\-\s]+\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b",
        "[REDACTED:ADDRESS]",
    ),
    _compile(
        "PERSON_NAME",
        r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",
        "[REDACTED:PERSON_NAME]",
        ignore_case=False,
    ),
)


def build_custom_patterns(custom_patterns: dict[str, str] | None) -> Iterable[PIIPattern]:
    if not custom_patterns:
        return ()
    return tuple(
        _compile(label=label.upper(), raw_pattern=pattern, placeholder=f"[REDACTED:{label.upper()}]")
        for label, pattern in custom_patterns.items()
    )
