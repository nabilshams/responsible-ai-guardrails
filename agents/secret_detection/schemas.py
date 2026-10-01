"""Versioned public contracts for runtime secret redaction."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from shared.guardrails.models import EntityResult


class SecretRedactionRequest(BaseModel):
    contract_version: Literal["1.0"] = "1.0"
    input: str = Field(min_length=1, max_length=100_000)
    correlation_id: str | None = Field(default=None, max_length=128)


class SecretRedactionResponse(BaseModel):
    contract_version: Literal["1.0"] = "1.0"
    redacted_text: str
    entities: list[EntityResult]
    entity_counts: dict[str, int]
    correlation_id: str
