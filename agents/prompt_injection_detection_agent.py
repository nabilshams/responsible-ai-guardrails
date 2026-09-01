"""Prompt injection detection guardrail placeholder."""

from agents.base import GuardrailAgent


class PromptInjectionDetectionAgent(GuardrailAgent):
    name = "prompt_injection_detection"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Add prompt attack heuristics and model-based checks in a future increment.",
        }
