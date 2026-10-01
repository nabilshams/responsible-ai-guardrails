"""Microsoft Foundry host for the Secret and Credential Detection Agent."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from agents.secret_detection.factory import create_service
from agents.secret_detection.schemas import SecretRedactionResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
service = create_service()
app = InvocationAgentServerHost()


def _extract_text(data: dict[str, Any]) -> str:
    version = data.get("contract_version", "1.0")
    if version != "1.0":
        raise ValueError('Unsupported "contract_version"; expected "1.0"')
    value = data.get("message") or data.get("input")
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Provide a non-empty "message" or "input" string')
    return value


@app.invoke_handler
async def handle_invoke(request: Request) -> JSONResponse | StreamingResponse:
    """Redact runtime secrets locally without invoking a model or external service."""
    try:
        body = await request.body()
        if len(body) > service.settings.secret_max_request_bytes:
            raise ValueError("Request exceeds the configured size limit")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        result = service.redact(
            _extract_text(data),
            correlation_id=str(request.state.invocation_id),
        )
        payload = SecretRedactionResponse(
            redacted_text=result.redacted_text,
            entities=result.entities,
            entity_counts=result.entity_counts,
            correlation_id=result.correlation_id,
        ).model_dump()
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JSONResponse(
            {"error": "invalid_request", "message": str(exc)},
            status_code=400,
        )
    except RuntimeError as exc:
        logger.warning(
            "Secret redaction request failed without logging source content: %s",
            type(exc).__name__,
        )
        return JSONResponse(
            {"error": "processing_failed", "message": "Secret redaction failed"},
            status_code=422,
        )

    async def events() -> AsyncIterator[str]:
        serialized = json.dumps(payload, separators=(",", ":"))
        yield f"data: {json.dumps({'type': 'token', 'content': serialized})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'full_text': serialized})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    app.run()
