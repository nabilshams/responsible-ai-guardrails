"""Construction for the Image Redaction Agent."""

from functools import lru_cache

from shared.guardrails.config import Settings
from shared.guardrails.file_services import ImageRedactionService


@lru_cache(maxsize=1)
def create_service() -> ImageRedactionService:
    """Create the process-wide stateless image redaction service."""
    return ImageRedactionService(Settings())
