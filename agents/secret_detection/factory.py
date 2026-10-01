"""Construction for the Secret and Credential Detection Agent."""

from functools import lru_cache

from shared.guardrails.config import Settings
from shared.guardrails.secrets import SecretRedactionService


@lru_cache(maxsize=1)
def create_service() -> SecretRedactionService:
    """Create the process-wide deterministic secret redaction service."""
    return SecretRedactionService(Settings())
