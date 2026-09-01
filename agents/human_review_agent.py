"""Human review orchestration guardrail placeholder."""

from agents.base import GuardrailAgent


class HumanReviewAgent(GuardrailAgent):
    name = "human_review"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Add human-in-the-loop escalation workflow in a future increment.",
        }
