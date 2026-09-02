"""Construction for the Document Redaction Agent."""

from functools import lru_cache

from shared.guardrails.config import Settings
from shared.guardrails.file_services import DocumentRedactionService


@lru_cache(maxsize=1)
def create_service() -> DocumentRedactionService:
    """Create the process-wide stateless document redaction service."""
    return DocumentRedactionService(Settings())
