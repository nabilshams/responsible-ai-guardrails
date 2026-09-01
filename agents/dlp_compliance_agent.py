"""DLP compliance guardrail placeholder."""

from agents.base import GuardrailAgent


class DLPComplianceAgent(GuardrailAgent):
    name = "dlp_compliance"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Add enterprise DLP policy evaluation in a future increment.",
        }
