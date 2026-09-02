from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shared.guardrails.azure_language import AzureLanguagePiiDetector


def make_detector(result: object) -> AzureLanguagePiiDetector:
    detector = AzureLanguagePiiDetector(
        "https://synthetic-language.example.test",
        Mock(),
        threshold=0.7,
        chunk_size=8,
    )
    detector._client = Mock()  # type: ignore[attr-defined]
    detector._client.recognize_pii_entities.return_value = [result]  # type: ignore[attr-defined]
    return detector


def test_maps_azure_entities_and_chunk_offsets() -> None:
    entity = SimpleNamespace(
        confidence_score=0.99,
        offset=1,
        length=3,
        category="Person",
        subcategory=None,
    )
    result = SimpleNamespace(is_error=False, entities=[entity])
    detector = make_detector(result)

    entities = detector.detect("12345678ABC", "en")

    assert len(entities) == 2
    assert entities[0].offset == 1
    assert entities[1].offset == 9
    assert all(item.source == "azure-ai-language" for item in entities)


def test_filters_entities_below_threshold() -> None:
    entity = SimpleNamespace(
        confidence_score=0.69,
        offset=0,
        length=3,
        category="Person",
        subcategory=None,
    )
    detector = make_detector(SimpleNamespace(is_error=False, entities=[entity]))

    assert detector.detect("Ada") == []


def test_raises_safe_error_for_azure_failure() -> None:
    error = SimpleNamespace(code="SyntheticFailure")
    detector = make_detector(SimpleNamespace(is_error=True, error=error))

    with pytest.raises(RuntimeError, match="SyntheticFailure"):
        detector.detect("synthetic")
