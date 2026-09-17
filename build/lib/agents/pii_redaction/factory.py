"""Single construction point shared by every hosting adapter."""

from functools import lru_cache

from shared.guardrails.config import Settings
from shared.guardrails.service import PiiRedactionService


@lru_cache(maxsize=1)
def create_service() -> PiiRedactionService:
    """Create the process-wide stateless redaction service."""
    return PiiRedactionService(Settings())
