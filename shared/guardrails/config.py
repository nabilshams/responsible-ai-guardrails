"""Environment-backed configuration with secure defaults."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import ReplacementStyle


class Settings(BaseSettings):
    """Application settings. Authentication always uses managed identity locally or in Azure."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    pii_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    pii_replacement_style: ReplacementStyle = ReplacementStyle.TOKEN
    pii_default_language: str = Field(default="en", min_length=2, max_length=12)
    pii_max_request_bytes: int = Field(default=1024 * 1024, ge=1024, le=5 * 1024 * 1024)
    pii_max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=50 * 1024 * 1024,
    )
    pii_allowed_origins: list[str] = []

    azure_ai_language_endpoint: str | None = None
    azure_document_intelligence_endpoint: str | None = None
    azure_document_pii_storage_endpoint: str | None = None
    azure_document_pii_source_container: str = "pii-source"
    azure_document_pii_target_container: str = "pii-target"
    azure_document_pii_api_version: str = "2026-05-01"
    document_pii_redaction_character: str = "*"
    document_pii_poll_interval_seconds: float = Field(default=1.0, ge=1.0, le=30.0)
    document_pii_request_timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    document_pii_job_timeout_seconds: float = Field(default=180.0, ge=30.0, le=600.0)

    @field_validator(
        "azure_ai_language_endpoint",
        "azure_document_intelligence_endpoint",
        "azure_document_pii_storage_endpoint",
    )
    @classmethod
    def require_https(cls, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise ValueError("Azure service endpoints must use HTTPS")
        return value.rstrip("/") if value else None

    @field_validator("document_pii_redaction_character")
    @classmethod
    def require_supported_redaction_character(cls, value: str) -> str:
        if value not in set("!#$%&*+-=?@^_~"):
            raise ValueError("Unsupported document PII redaction character")
        return value
