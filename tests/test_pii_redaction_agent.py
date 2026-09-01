from agents.pii_redaction_agent import PIIRedactionAgent


def test_redacts_supported_entities():
    agent = PIIRedactionAgent()
    text = (
        "Mr. John Doe lives at 123 Main Street, email john.doe@example.com, "
        "phone 555-123-4567, license CA1234567, passport A12345678, "
        "card 4111 1111 1111 1111, tax id 123-45-6789."
    )

    result = agent.redact_text(text)

    assert "[REDACTED:PERSON_NAME]" in result.redacted_text
    assert "[REDACTED:ADDRESS]" in result.redacted_text
    assert "[REDACTED:EMAIL]" in result.redacted_text
    assert "[REDACTED:PHONE]" in result.redacted_text
    assert "[REDACTED:DRIVER_LICENSE]" in result.redacted_text
    assert "[REDACTED:PASSPORT]" in result.redacted_text
    assert "[REDACTED:CREDIT_CARD]" in result.redacted_text
    assert "[REDACTED:TAX_ID]" in result.redacted_text


def test_redacts_custom_sensitive_patterns():
    agent = PIIRedactionAgent(custom_patterns={"employee_id": r"EMP-\d{4}"})

    result = agent.redact_text("Escalate ticket for EMP-4821 immediately")

    assert "[REDACTED:EMPLOYEE_ID]" in result.redacted_text


def test_prompt_response_document_helpers_use_same_redaction():
    agent = PIIRedactionAgent()
    payload = "Reach me at jane@example.com"

    assert agent.redact_prompt(payload).redacted_text == "Reach me at [REDACTED:EMAIL]"
    assert agent.redact_response(payload).redacted_text == "Reach me at [REDACTED:EMAIL]"
    assert agent.redact_document(payload).redacted_text == "Reach me at [REDACTED:EMAIL]"
    assert agent.redact_image_text(payload).redacted_text == "Reach me at [REDACTED:EMAIL]"
