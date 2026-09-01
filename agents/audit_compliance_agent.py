"""Audit and compliance guardrail placeholder."""

from agents.base import GuardrailAgent


class AuditComplianceAgent(GuardrailAgent):
    name = "audit_compliance"

    def run(self, content: str) -> dict:
        return {
            "agent": self.name,
            "status": "not_implemented",
            "message": "Add audit logging and evidence generation in a future increment.",
        }
