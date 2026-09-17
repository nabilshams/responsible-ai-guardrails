"""External API contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.guardrails.models import EntityResult


class TextRedactionRequest(BaseModel):
    input: str = Field(min_length=1, max_length=100_000)
    language: str = Field(default="en", min_length=2, max_length=12)
    correlation_id: str | None = Field(default=None, max_length=128)


class RedactionResponse(BaseModel):
    redacted_text: str
    entities: list[EntityResult]
    entity_counts: dict[str, int]
    correlation_id: str
