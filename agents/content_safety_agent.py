"""Content safety guardrail placeholder."""

from agents.base import GuardrailAgent


class ContentSafetyAgent(GuardrailAgent):
    name = "content_safety"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Integrate Azure AI Content Safety policies in a future increment.",
        }
