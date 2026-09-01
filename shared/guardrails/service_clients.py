"""Azure service abstraction layer for pluggable guardrail implementations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AzureServiceConfig:
    foundry_project_endpoint: str | None = None
    language_endpoint: str | None = None
    vision_endpoint: str | None = None
    content_understanding_endpoint: str | None = None
    document_intelligence_endpoint: str | None = None


class AzureServiceClients:
    """Placeholder abstraction for Azure AI Foundry service clients.

    This repository starts with regex-based local guardrails and can be extended to
    wire Azure AI Language, Vision, Content Understanding, and Document Intelligence
    clients through this class.
    """

    def __init__(self, config: AzureServiceConfig | None = None) -> None:
        self.config = config or AzureServiceConfig()
