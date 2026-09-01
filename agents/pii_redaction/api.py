"""FastAPI adapter for application-to-application guardrail calls."""

from __future__ import annotations

import base64

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from shared.guardrails.documents import UnsupportedDocumentError

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


def _response(result: object) -> RedactionResponse:
    text_result = getattr(result, "text_result", result)
    content = getattr(result, "content", None)
    return RedactionResponse(
        redacted_text=text_result.redacted_text,
        entities=text_result.entities,
        entity_counts=text_result.entity_counts,
        correlation_id=text_result.correlation_id,
        redacted_file_base64=base64.b64encode(content).decode("ascii") if content else None,
        redacted_file_content_type=getattr(result, "content_type", None),
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@app.post("/v1/redact/file", response_model=RedactionResponse)
async def redact_file_endpoint(
    file: UploadFile = File(...),
    language: str = "en",
    x_correlation_id: str | None = Header(default=None, max_length=128),
) -> RedactionResponse:
    content_type = file.content_type or "application/octet-stream"
    content = await file.read(service.settings.pii_max_upload_bytes + 1)
    try:
        result = service.redact_file(
            content,
            content_type,
            file.filename or "document",
            language=language,
            correlation_id=x_correlation_id,
        )
        return _response(result)
    except (UnsupportedDocumentError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
