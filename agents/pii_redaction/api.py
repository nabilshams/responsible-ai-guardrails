"""FastAPI adapter for application-to-application guardrail calls."""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from shared.guardrails.models import RedactionResult

from .factory import create_service
from .schemas import RedactionResponse, TextRedactionRequest

app = FastAPI(
    title="PII Redaction Agent",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    description="Detects and irreversibly redacts PII without persisting source content.",
)
service = create_service()

if service.settings.pii_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=service.settings.pii_allowed_origins,
        allow_credentials=False,
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )


def _response(result: RedactionResult) -> RedactionResponse:
    return RedactionResponse(
        redacted_text=result.redacted_text,
        entities=result.entities,
        entity_counts=result.entity_counts,
        correlation_id=result.correlation_id,
    )


@app.get("/healthz", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/v1/redact/text", response_model=RedactionResponse)
@app.post("/v1/redact/prompt", response_model=RedactionResponse)
@app.post("/v1/redact/response", response_model=RedactionResponse)
def redact_text_endpoint(
    request: TextRedactionRequest,
    x_correlation_id: str | None = Header(default=None, max_length=128),
) -> RedactionResponse:
    try:
        result = service.redact(
            request.input,
            language=request.language,
            correlation_id=x_correlation_id or request.correlation_id,
        )
        return _response(result)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
