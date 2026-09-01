"""Image redaction guardrail placeholder."""

from agents.base import GuardrailAgent


class ImageRedactionAgent(GuardrailAgent):
    name = "image_redaction"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Wire OCR and image masking with Azure AI Vision in a future increment.",
        }
