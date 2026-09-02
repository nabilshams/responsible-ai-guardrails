"""Typed contracts shared by every guardrail implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReplacementStyle(StrEnum):
    """Supported non-reversible replacement strategies."""

    TOKEN = "token"  # noqa: S105 - redaction style, not a credential
    MASK = "mask"


@dataclass(frozen=True, slots=True)
class DetectedEntity:
    """Internal entity representation; value is deliberately excluded from repr."""

    category: str
    offset: int
    length: int
    confidence: float
    source: str
    value: str = field(repr=False, compare=False)
    subcategory: str | None = None
    replacement: str | None = None

    @property
    def end(self) -> int:
        return self.offset + self.length


class EntityResult(BaseModel):
    """Public metadata that never returns the original sensitive value."""

    model_config = ConfigDict(frozen=True)

    category: str
    offset: int = Field(ge=0)
    length: int = Field(gt=0)
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    subcategory: str | None = None


class RedactionResult(BaseModel):
    """Safe result returned to callers and audit sinks."""

    redacted_text: str
    entities: list[EntityResult]
    entity_counts: dict[str, int]
    original_length: int = Field(ge=0)
    redacted_length: int = Field(ge=0)
    correlation_id: str


@dataclass(frozen=True, slots=True)
class TextRegion:
    """A source word polygon mapped to a text span."""

    offset: int
    length: int
    polygon: tuple[float, ...]
    page_number: int = 1

    @property
    def end(self) -> int:
        return self.offset + self.length


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Text and optional source geometry produced by a document extractor."""

    text: str
    regions: tuple[TextRegion, ...] = ()
    page_width: float | None = None
    page_height: float | None = None
