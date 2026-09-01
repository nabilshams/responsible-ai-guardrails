from shared.guardrails.models import DetectedEntity, ReplacementStyle
from shared.guardrails.redactor import normalize_entities, redact_text


def entity(value: str, offset: int, confidence: float = 0.9) -> DetectedEntity:
    return DetectedEntity("Email", offset, len(value), confidence, "test", value)


def test_redacts_in_reverse_order_and_does_not_return_values() -> None:
    text = "Send a@example.test to b@example.test"
    entities = [entity("a@example.test", 5), entity("b@example.test", 23)]

    result = redact_text(text, entities, correlation_id="test-id")

    assert result.redacted_text == "Send [REDACTED:EMAIL] to [REDACTED:EMAIL]"
    assert "a@example.test" not in result.model_dump_json()
    assert result.entity_counts == {"Email": 2}


def test_overlap_prefers_higher_confidence() -> None:
    low = entity("abcdef", 0, 0.7)
    high = DetectedEntity("Custom", 2, 3, 0.99, "test", "cde")

    selected = normalize_entities([low, high], text_length=6, threshold=0.5)

    assert selected == [high]


def test_mask_preserves_original_length() -> None:
    result = redact_text(
        "secret",
        [DetectedEntity("Custom", 0, 6, 1.0, "test", "secret")],
        style=ReplacementStyle.MASK,
        correlation_id="test-id",
    )
    assert result.redacted_text == "██████"
    assert result.redacted_length == result.original_length
