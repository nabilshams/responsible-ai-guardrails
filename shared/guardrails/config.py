"""Environment-backed configuration with secure defaults."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import ReplacementStyle


class CustomPattern(BaseModel):
    """Tenant-defined sensitive-data pattern."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    pattern: str = Field(min_length=1, max_length=512)
    replacement: str | None = Field(default=None, max_length=80)

    @field_validator("pattern")
    @classmethod
    def compile_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regular expression: {exc}") from exc
        return value


class Settings(BaseSettings):
    """Application settings. Authentication always uses managed identity locally or in Azure."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    pii_backend: Literal["local", "azure", "hybrid"] = "local"
    pii_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    pii_replacement_style: ReplacementStyle = ReplacementStyle.TOKEN
    pii_default_language: str = Field(default="en", min_length=2, max_length=12)
    pii_max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    pii_allowed_origins: list[str] = []
    pii_custom_patterns: list[CustomPattern] = []

    azure_ai_language_endpoint: str | None = None
    azure_document_intelligence_endpoint: str | None = None
    azure_content_understanding_endpoint: str | None = None

    @field_validator(
        "azure_ai_language_endpoint",
        "azure_document_intelligence_endpoint",
        "azure_content_understanding_endpoint",
    )
    @classmethod
    def require_https(cls, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise ValueError("Azure service endpoints must use HTTPS")
        return value.rstrip("/") if value else None
