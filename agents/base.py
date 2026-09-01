"""Core interfaces for guardrail agents."""

from abc import ABC, abstractmethod


class GuardrailAgent(ABC):
    """Base type for all repository guardrail agents."""

    name: str

    @abstractmethod
    def run(self, content: str) -> dict:
        """Run the agent over the provided content."""
