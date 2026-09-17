"""Span normalization and non-reversible text redaction."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .models import DetectedEntity, EntityResult, RedactionResult, ReplacementStyle


def normalize_entities(
    entities: Iterable[DetectedEntity], text_length: int, threshold: float
) -> list[DetectedEntity]:
    """Validate spans and resolve overlap by confidence, then span length."""
    candidates = [
        entity
        for entity in entities
        if entity.confidence >= threshold
        and entity.offset >= 0
        and entity.length > 0
        and entity.end <= text_length
    ]
    ranked = sorted(candidates, key=lambda item: (-item.confidence, -item.length, item.offset))
    selected: list[DetectedEntity] = []
    for entity in ranked:
        if any(entity.offset < current.end and current.offset < entity.end for current in selected):
            continue
        selected.append(entity)
    return sorted(selected, key=lambda item: item.offset)


def redact_text(
    text: str,
    entities: Iterable[DetectedEntity],
    *,
    threshold: float = 0.70,
    style: ReplacementStyle = ReplacementStyle.TOKEN,
    correlation_id: str,
) -> RedactionResult:
    """Redact selected spans without returning sensitive source values."""
    selected = normalize_entities(entities, len(text), threshold)
    output = text
    for entity in reversed(selected):
        if entity.replacement:
            replacement = entity.replacement
        elif style == ReplacementStyle.MASK:
            replacement = "█" * entity.length
        else:
            safe_category = entity.category.upper().replace(" ", "_")
            replacement = f"[REDACTED:{safe_category}]"
        output = output[: entity.offset] + replacement + output[entity.end :]

    counts = Counter(entity.category for entity in selected)
    public_entities = [
        EntityResult(
            category=entity.category,
            subcategory=entity.subcategory,
            offset=entity.offset,
            length=entity.length,
            confidence=entity.confidence,
            source=entity.source,
        )
        for entity in selected
    ]
    return RedactionResult(
        redacted_text=output,
        entities=public_entities,
        entity_counts=dict(sorted(counts.items())),
        original_length=len(text),
        redacted_length=len(output),
        correlation_id=correlation_id,
    )
