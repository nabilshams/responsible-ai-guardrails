import json
from pathlib import Path

from shared.evaluations.metrics import score_spans
from shared.guardrails.detectors import RegexPiiDetector

DATASET = Path("shared/evaluations/datasets/pii_redaction.jsonl")


def test_evaluation_dataset_has_only_synthetic_markers() -> None:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    assert len(rows) >= 5
    assert all(row["synthetic"] is True for row in rows)


def test_offline_span_evaluation_baseline() -> None:
    detector = RegexPiiDetector()
    text = "Contact synthetic.user@example.test"
    predicted = detector.detect(text)
    expected = [(8, 27, "Email")]

    score = score_spans(predicted, expected)

    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
