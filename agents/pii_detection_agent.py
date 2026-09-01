"""PII detection guardrail stub."""

from agents.base import GuardrailAgent
from agents.pii_redaction_agent import PIIRedactionAgent


class PIIDetectionAgent(GuardrailAgent):
    name = "pii_detection"

    def __init__(self) -> None:
        self._redactor = PIIRedactionAgent()

    def run(self, content: str) -> dict:
        entities = self._redactor._detect_entities(content)
        return {
            "agent": self.name,
            "entities": [entity.__dict__ for entity in entities],
            "contains_pii": bool(entities),
        }
