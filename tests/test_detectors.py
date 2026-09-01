from shared.guardrails.config import CustomPattern
from shared.guardrails.detectors import RegexPiiDetector


def test_detects_structured_pii_without_invalid_card_numbers() -> None:
    text = "Email ada@example.test, phone +1 425-555-0199, card 4111 1111 1111 1111."
    entities = RegexPiiDetector().detect(text)
    categories = {entity.category for entity in entities}

    assert {"Email", "PhoneNumber", "CreditCardNumber"} <= categories
    assert all(entity.value == text[entity.offset : entity.end] for entity in entities)


def test_rejects_failed_luhn_number() -> None:
    entities = RegexPiiDetector().detect("Card 4111 1111 1111 1112")
    assert "CreditCardNumber" not in {entity.category for entity in entities}


def test_custom_pattern_and_replacement() -> None:
    detector = RegexPiiDetector(
        [CustomPattern(name="EmployeeId", pattern=r"EMP-\d{6}", replacement="[EMPLOYEE]")]
    )
    entity = detector.detect("Owner EMP-123456")[0]

    assert entity.category == "Custom:EmployeeId"
    assert entity.replacement == "[EMPLOYEE]"
