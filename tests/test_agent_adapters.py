import importlib
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shared.guardrails.config import Settings
from shared.guardrails.models import DetectedEntity
from shared.guardrails.service import PiiRedactionService


class StubAzureLanguageDetector:
    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        value = "synthetic.user@example.test"
        if value not in text:
            return []
        offset = text.index(value)
        return [DetectedEntity("Email", offset, len(value), 0.99, "azure-ai-language", value)]


def make_service() -> PiiRedactionService:
    return PiiRedactionService(Settings(), detector=StubAzureLanguageDetector())


def load_adapter(module_name: str, monkeypatch: Any) -> Any:
    monkeypatch.setenv("AZURE_AI_LANGUAGE_ENDPOINT", "https://synthetic-language.example.test")
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "service", make_service())
    return module


def test_rest_adapter_health_and_text_redaction(monkeypatch: Any) -> None:
    api = load_adapter("agents.pii_redaction.api", monkeypatch)
    client = TestClient(api.app)

    health = client.get("/healthz")
    response = client.post(
        "/v1/redact/text",
        json={"input": "Contact synthetic.user@example.test", "language": "en"},
        headers={"X-Correlation-ID": "synthetic-correlation"},
    )

    assert health.json() == {"status": "healthy"}
    assert response.status_code == 200
    assert response.json()["redacted_text"] == "Contact [REDACTED:EMAIL]"
    assert response.json()["correlation_id"] == "synthetic-correlation"


def test_rest_adapter_rejects_processing_error(monkeypatch: Any) -> None:
    api = load_adapter("agents.pii_redaction.api", monkeypatch)
    failure = RuntimeError("synthetic failure")
    monkeypatch.setattr(
        api.service,
        "redact",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure),
    )

    response = TestClient(api.app).post("/v1/redact/text", json={"input": "synthetic"})

    assert response.status_code == 422
    assert response.json()["detail"] == "synthetic failure"


class FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.state = SimpleNamespace(invocation_id="synthetic-invocation")

    async def body(self) -> bytes:
        return self._body


async def stream_payload(response: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        line = chunk.decode() if isinstance(chunk, bytes) else chunk
        for item in line.splitlines():
            if item.startswith("data: "):
                events.append(json.loads(item[6:]))
    return events


@pytest.mark.asyncio
async def test_invocations_adapter_redacts_text(monkeypatch: Any) -> None:
    main = load_adapter("agents.pii_redaction.main", monkeypatch)
    request = FakeRequest(json.dumps({"input": "Contact synthetic.user@example.test"}).encode())

    response = await main.handle_invoke(request)
    events = await stream_payload(response)

    assert response.media_type == "text/event-stream"
    assert events[-1]["type"] == "done"
    assert "[REDACTED:EMAIL]" in events[-1]["full_text"]


@pytest.mark.asyncio
async def test_invocations_adapter_rejects_non_text_payload(monkeypatch: Any) -> None:
    main = load_adapter("agents.pii_redaction.main", monkeypatch)

    response = await main.handle_invoke(FakeRequest(b'{"document": {}}'))

    assert response.status_code == 400
    assert b"invalid_request" in response.body
