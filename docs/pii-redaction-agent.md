# PII Redaction Agent

`PIIRedactionAgent` detects and redacts:

- Person names (salutation-based)
- Email addresses
- Phone numbers
- Physical addresses
- Driver licence numbers
- Passport numbers
- Credit card numbers
- Tax identifiers
- Custom sensitive patterns

## Usage

```python
from agents.pii_redaction_agent import PIIRedactionAgent

agent = PIIRedactionAgent(custom_patterns={"employee_id": r"EMP-\\d{4}"})
result = agent.redact_text("Contact john@example.com about EMP-1234")
print(result.redacted_text)
```

## Notes

- The first release uses deterministic regex guardrails.
- Azure service clients can be integrated via `shared/guardrails/service_clients.py`.
