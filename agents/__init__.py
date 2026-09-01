"""Agent exports and registry."""

from agents.audit_compliance_agent import AuditComplianceAgent
from agents.content_safety_agent import ContentSafetyAgent
from agents.dlp_compliance_agent import DLPComplianceAgent
from agents.human_review_agent import HumanReviewAgent
from agents.image_redaction_agent import ImageRedactionAgent
from agents.pii_detection_agent import PIIDetectionAgent
from agents.pii_redaction_agent import PIIRedactionAgent
from agents.prompt_injection_detection_agent import PromptInjectionDetectionAgent
from agents.secret_credential_detection_agent import SecretCredentialDetectionAgent

AGENT_REGISTRY = {
    "pii_redaction": PIIRedactionAgent,
    "pii_detection": PIIDetectionAgent,
    "image_redaction": ImageRedactionAgent,
    "content_safety": ContentSafetyAgent,
    "prompt_injection_detection": PromptInjectionDetectionAgent,
    "secret_credential_detection": SecretCredentialDetectionAgent,
    "dlp_compliance": DLPComplianceAgent,
    "human_review": HumanReviewAgent,
    "audit_compliance": AuditComplianceAgent,
}

__all__ = [
    "AGENT_REGISTRY",
    "PIIRedactionAgent",
    "PIIDetectionAgent",
    "ImageRedactionAgent",
    "ContentSafetyAgent",
    "PromptInjectionDetectionAgent",
    "SecretCredentialDetectionAgent",
    "DLPComplianceAgent",
    "HumanReviewAgent",
    "AuditComplianceAgent",
]
