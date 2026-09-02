"""Microsoft Foundry Invocations-protocol host for the PII Redaction Agent."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from agents.pii_redaction.factory import create_service
from shared.guardrails.models import RedactionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
service = create_service()
app = InvocationAgentServerHost()


def _extract_text(data: dict[str, Any]) -> str:
    value = data.get("message") or data.get("input")
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Provide a non-empty "message" or "input" string')
    return value


def _safe_payload(result: RedactionResult) -> dict[str, Any]:
    return result.model_dump()


@app.invoke_handler
async def handle_invoke(request: Request) -> JSONResponse | StreamingResponse:
    """Redact text using Azure AI Language without invoking a generative model."""
    try:
        body = await request.body()
        if len(body) > service.settings.pii_max_request_bytes:
            raise ValueError("Request exceeds the configured size limit")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        language = str(data.get("language") or service.settings.pii_default_language)
        correlation_id = str(request.state.invocation_id)
        result = service.redact(
            _extract_text(data),
            language=language,
            correlation_id=correlation_id,
        )
        payload = _safe_payload(result)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JSONResponse(
            {"error": "invalid_request", "message": str(exc)},
            status_code=400,
        )
    except RuntimeError as exc:
        logger.warning(
            "Redaction request failed without logging source content: %s",
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
