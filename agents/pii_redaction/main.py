"""Microsoft Foundry Invocations-protocol host for the PII Redaction Agent."""

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

from agents.pii_redaction.factory import create_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
service = create_service()
app = InvocationAgentServerHost()


def _extract_text(data: dict[str, Any]) -> str:
    value = data.get("message") or data.get("input")
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Provide a non-empty "message" or "input" string')
    return value


def _safe_payload(result: Any) -> dict[str, Any]:
    text_result = getattr(result, "text_result", result)
    content = getattr(result, "content", None)
    payload: dict[str, Any] = text_result.model_dump()
    if content:
        payload["redacted_file_base64"] = base64.b64encode(content).decode("ascii")
        payload["redacted_file_content_type"] = result.content_type
    return payload


@app.invoke_handler
async def handle_invoke(request: Request) -> JSONResponse | StreamingResponse:
    """Redact text or a base64-encoded document without invoking a generative model."""
    try:
        body = await request.body()
        if len(body) > service.settings.pii_max_upload_bytes * 2:
            raise ValueError("Request exceeds the configured size limit")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        language = str(data.get("language") or service.settings.pii_default_language)
        correlation_id = str(request.state.invocation_id)
        document = data.get("document")
        if isinstance(document, dict):
            encoded = document.get("content_base64")
            if not isinstance(encoded, str):
                raise ValueError("document.content_base64 is required")
            content = base64.b64decode(encoded, validate=True)
            result = service.redact_file(
                content,
                str(document.get("content_type") or "application/octet-stream"),
                str(document.get("filename") or "document"),
                language=language,
                correlation_id=correlation_id,
            )
        else:
            result = service.redact(
                _extract_text(data),
                language=language,
                correlation_id=correlation_id,
            )
        payload = _safe_payload(result)
    except (UnicodeDecodeError, json.JSONDecodeError, binascii.Error, ValueError) as exc:
        return JSONResponse(
            {"error": "invalid_request", "message": str(exc)},
            status_code=400,
        )
    except RuntimeError as exc:
        logger.warning("Redaction request failed without logging source content: %s", type(exc).__name__)
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
