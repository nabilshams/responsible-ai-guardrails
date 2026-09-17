"""Construction for the Document Redaction Agent."""

from functools import lru_cache

from shared.guardrails.config import Settings
from shared.guardrails.file_services import DocumentAgentService


@lru_cache(maxsize=1)
def create_service() -> DocumentAgentService:
    """Create the process-wide stateless document redaction service."""
    return DocumentAgentService(Settings())
