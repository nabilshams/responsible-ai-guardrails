"""Deterministic PII evaluation metrics that require no judge model."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from shared.guardrails.models import DetectedEntity


@dataclass(frozen=True, slots=True)
class SpanScore:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def score_spans(
    predicted: Iterable[DetectedEntity], expected: Iterable[tuple[int, int, str]]
) -> SpanScore:
    predicted_set = {(item.offset, item.length, item.category) for item in predicted}
    expected_set = set(expected)
    true_positives = len(predicted_set & expected_set)
    false_positives = len(predicted_set - expected_set)
    false_negatives = len(expected_set - predicted_set)
    precision = true_positives / (true_positives + false_positives) if predicted_set else 0.0
    recall = true_positives / (true_positives + false_negatives) if expected_set else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return SpanScore(precision, recall, f1, true_positives, false_positives, false_negatives)
