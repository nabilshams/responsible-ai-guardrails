import base64
import importlib
import json
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from shared.guardrails.file_services import ImageRedactionResult
from shared.guardrails.models import RedactionResult


class FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.state = SimpleNamespace(invocation_id="synthetic-invocation")

    async def body(self) -> bytes:
        return self._body


async def stream_payload(response: Any) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        line = chunk.decode() if isinstance(chunk, bytes) else chunk
        for item in line.splitlines():
            if item.startswith("data: "):
                events.append(json.loads(item[6:]))
    return json.loads(events[-1]["full_text"])


def redaction_result() -> RedactionResult:
    return RedactionResult(
        redacted_text="Contact [REDACTED:EMAIL]",
        entities=[],
        entity_counts={"Email": 1},
        original_length=35,
        redacted_length=24,
        correlation_id="synthetic-invocation",
    )


def load_adapter(module_name: str, monkeypatch: Any) -> Any:
    monkeypatch.setenv("AZURE_AI_LANGUAGE_ENDPOINT", "https://language.example.test")
    monkeypatch.setenv(
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "https://documents.example.test",
    )
    return importlib.import_module(module_name)


@pytest.mark.asyncio
async def test_document_agent_accepts_base64_document(monkeypatch: Any) -> None:
    main = load_adapter("agents.document_redaction.main", monkeypatch)
    monkeypatch.setattr(main.service, "redact", lambda *args, **kwargs: redaction_result())
    request = FakeRequest(
        json.dumps(
            {
                "document": {
                    "content_base64": base64.b64encode(b"synthetic document").decode(),
                    "content_type": "text/plain",
                    "filename": "synthetic.txt",
                }
            }
        ).encode()
    )

    response = await main.handle_invoke(request)
    payload = await stream_payload(response)

    assert payload["redacted_text"] == "Contact [REDACTED:EMAIL]"


@pytest.mark.asyncio
async def test_image_agent_returns_only_redacted_image(monkeypatch: Any) -> None:
    main = load_adapter("agents.image_redaction.main", monkeypatch)
    source = Image.new("RGB", (2, 2), "black")
    buffer = BytesIO()
    source.save(buffer, format="PNG")
    result = ImageRedactionResult(redaction_result(), buffer.getvalue())
    monkeypatch.setattr(main.service, "redact", lambda *args, **kwargs: result)
    request = FakeRequest(
        json.dumps(
            {
                "image": {
                    "content_base64": base64.b64encode(b"synthetic image").decode(),
                    "content_type": "image/png",
                    "filename": "synthetic.png",
                }
            }
        ).encode()
    )

    response = await main.handle_invoke(request)
    payload = await stream_payload(response)

    assert payload["redacted_image_content_type"] == "image/png"
    assert base64.b64decode(payload["redacted_image_base64"]) == buffer.getvalue()
    assert "synthetic image" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_specialist_agents_reject_wrong_contract(monkeypatch: Any) -> None:
    document_main = load_adapter("agents.document_redaction.main", monkeypatch)
    image_main = load_adapter("agents.image_redaction.main", monkeypatch)

    document_response = await document_main.handle_invoke(FakeRequest(b'{"input":"text"}'))
    image_response = await image_main.handle_invoke(FakeRequest(b'{"document":{}}'))

    assert document_response.status_code == 400
    assert image_response.status_code == 400
