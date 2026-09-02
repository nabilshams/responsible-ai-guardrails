"""Microsoft Foundry host for the Document Redaction Agent."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from agents.document_redaction.factory import create_service
from shared.guardrails.documents import UnsupportedDocumentError
from shared.guardrails.native_document_pii import NativeDocumentRedactionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
service = create_service()
app = InvocationAgentServerHost()


def _decode_document(data: dict[str, Any]) -> tuple[bytes, str, str]:
    document = data.get("document")
    if not isinstance(document, dict):
        raise ValueError('Provide a "document" object')
    encoded = document.get("content_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("document.content_base64 is required")
    content_type = str(document.get("content_type") or "application/octet-stream")
    filename = str(document.get("filename") or "document")
    return base64.b64decode(encoded, validate=True), content_type, filename


@app.invoke_handler
async def handle_invoke(request: Request) -> JSONResponse | StreamingResponse:
    """Extract document text and redact PII using Azure services."""
    try:
        body = await request.body()
        if len(body) > service.settings.pii_max_upload_bytes * 2:
            raise ValueError("Request exceeds the configured size limit")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        content, content_type, filename = _decode_document(data)
        result = service.redact(
            content,
            content_type,
            filename,
            language=str(data.get("language") or service.settings.pii_default_language),
            correlation_id=str(request.state.invocation_id),
        )
        if isinstance(result, NativeDocumentRedactionResult):
            payload = {
                "redacted_document_base64": base64.b64encode(result.content).decode("ascii"),
                "content_type": result.content_type,
                "filename": result.filename,
                "correlation_id": result.correlation_id,
            }
        else:
            payload = result.model_dump()
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
        UnsupportedDocumentError,
        ValueError,
    ) as exc:
        return JSONResponse(
            {"error": "invalid_request", "message": str(exc)},
            status_code=400,
        )
    except RuntimeError as exc:
        logger.warning(
            "Document redaction failed without logging source content: %s",
            type(exc).__name__,
        )
        return JSONResponse(
            {"error": "processing_failed", "message": str(exc)},
            status_code=422,
        )

    async def events() -> AsyncIterator[str]:
        serialized = json.dumps(payload, separators=(",", ":"))
        yield f"data: {json.dumps({'type': 'token', 'content': serialized})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'full_text': serialized})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    app.run()
