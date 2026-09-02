import json
from pathlib import Path

from shared.evaluations.metrics import score_spans
from shared.guardrails.models import DetectedEntity

DATASET = Path("shared/evaluations/datasets/pii_redaction.jsonl")


def test_evaluation_dataset_has_only_synthetic_markers() -> None:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    assert len(rows) >= 5
    assert all(row["synthetic"] is True for row in rows)


def test_offline_span_evaluation_baseline() -> None:
    predicted = [
        DetectedEntity(
            category="Email",
            offset=8,
            length=27,
            confidence=0.99,
            source="azure-ai-language",
            value="synthetic.user@example.test",
        )
    ]
    expected = [(8, 27, "Email")]

    score = score_spans(predicted, expected)

    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
