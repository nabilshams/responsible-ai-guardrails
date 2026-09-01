"""Secret and credential detection guardrail placeholder."""

from agents.base import GuardrailAgent


class SecretCredentialDetectionAgent(GuardrailAgent):
    name = "secret_credential_detection"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Integrate secret scanning controls in a future increment.",
        }
