"""PII redaction agent implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agents.base import GuardrailAgent
from shared.guardrails.pii_patterns import DEFAULT_PII_PATTERNS, PIIPattern, build_custom_patterns


@dataclass(frozen=True)
class DetectedEntity:
    label: str
    value: str
    start: int
    end: int
    placeholder: str


@dataclass(frozen=True)
class RedactionResult:
    original_text: str
    redacted_text: str
    entities: tuple[DetectedEntity, ...]


class PIIRedactionAgent(GuardrailAgent):
    """Detects and redacts PII in text-like payloads."""

    name = "pii_redaction"

    def __init__(self, custom_patterns: dict[str, str] | None = None) -> None:
        custom = tuple(build_custom_patterns(custom_patterns))
        self._patterns: tuple[PIIPattern, ...] = (*DEFAULT_PII_PATTERNS, *custom)

    def _detect_entities(self, content: str) -> list[DetectedEntity]:
        entities: list[DetectedEntity] = []
        for pii_pattern in self._patterns:
            for match in pii_pattern.pattern.finditer(content):
                entities.append(
                    DetectedEntity(
                        label=pii_pattern.label,
                        value=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        placeholder=pii_pattern.placeholder,
                    )
                )

        entities.sort(key=lambda item: (item.start, -(item.end - item.start)))
        non_overlapping: list[DetectedEntity] = []
        cursor = -1
        for entity in entities:
            if entity.start < cursor:
                continue
            non_overlapping.append(entity)
            cursor = entity.end
        return non_overlapping

    def redact_text(self, content: str) -> RedactionResult:
        entities = self._detect_entities(content)
        if not entities:
            return RedactionResult(original_text=content, redacted_text=content, entities=())

        parts: list[str] = []
        last_idx = 0
        for entity in entities:
            parts.append(content[last_idx:entity.start])
            parts.append(entity.placeholder)
            last_idx = entity.end
        parts.append(content[last_idx:])

        return RedactionResult(
            original_text=content,
            redacted_text="".join(parts),
            entities=tuple(entities),
        )

    def redact_document(self, content: str) -> RedactionResult:
        return self.redact_text(content)

    def redact_prompt(self, content: str) -> RedactionResult:
        return self.redact_text(content)

    def redact_response(self, content: str) -> RedactionResult:
        return self.redact_text(content)

    def redact_image_text(self, ocr_content: str) -> RedactionResult:
        return self.redact_text(ocr_content)

    def run(self, content: str) -> dict:
        result = self.redact_text(content)
        return {
            "agent": self.name,
            "redacted_text": result.redacted_text,
            "entities": [entity.__dict__ for entity in result.entities],
        }
