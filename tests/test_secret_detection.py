from __future__ import annotations

import importlib
import inspect
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from shared.guardrails.config import Settings
from shared.guardrails.secrets import SecretDetector, SecretRedactionService


@pytest.mark.parametrize(
    ("category", "text"),
    [
        (
            "PrivateKey",
            "key=-----BEGIN PRIVATE KEY-----\nSYNTHETIC_TEST_DATA\n"
            "-----END PRIVATE KEY-----",
        ),
        (
            "GitHubToken",
            "token=github_pat_SYNTHETIC0123456789ABCDE",
        ),
        (
            "ProviderApiKey",
            "key=sk-synthetic_TEST_0123456789ABCDE",
        ),
        (
            "JsonWebToken",
            "jwt=eyJzeW50aGV0aWMiOnRydWV9.eyJzdWIiOiJleGFtcGxlIn0."
            "synthetic_signature",
        ),
        (
            "BearerToken",
            "Authorization: Bearer synthetic_runtime_token_Q7v9X2m4",
        ),
        (
            "SasSignature",
            "https://storage.example.test/blob?sv=synthetic&sig="
            "synthetic_signature_Q7v9X2m4",
        ),
        (
            "ConnectionStringSecret",
            "AccountName=synthetic;AccountKey=synthetic_account_key_Q7v9X2m4;",
        ),
        (
            "GenericSecret",
            "client_secret=synthetic_client_secret_Q7v9X2m4",
        ),
    ],
)
def test_detects_each_supported_secret_without_exposing_values(
    category: str,
    text: str,
) -> None:
    detector = SecretDetector()

    detections = detector.detect(text)

    assert any(item.category == category for item in detections)
    assert all(item.value not in repr(item) for item in detections)


def test_generic_detection_requires_context_entropy_and_minimum_length() -> None:
    detector = SecretDetector()

    assert detector.detect("password=short") == []
    assert detector.detect("api_key=aaaaaaaaaaaaaaaaaaaa") == []
    assert detector.detect("Use the word password in this sentence.") == []
    assert detector.detect("api_key=${SYNTHETIC_SECRET}") == []


def test_additional_keyword_is_literal_and_rejects_unsafe_patterns() -> None:
    detector = SecretDetector(additional_keywords=("contoso_credential",))

    detections = detector.detect(
        "contoso_credential=synthetic_tenant_value_Q7v9X2m4"
    )

    assert [item.category for item in detections] == ["GenericSecret"]
    with pytest.raises(ValueError, match="safe identifier"):
        SecretDetector(additional_keywords=("unsafe.*pattern",))


def test_specific_signature_wins_overlap_with_generic_detection() -> None:
    value = "sk-synthetic_TEST_0123456789ABCDE"
    service = SecretRedactionService(Settings())

    result = service.redact(f"api_key={value}", correlation_id="synthetic-correlation")

    assert result.redacted_text == "api_key=[REDACTED:PROVIDERAPIKEY]"
    assert result.entity_counts == {"ProviderApiKey": 1}
    assert value not in result.model_dump_json()


def test_redacts_multiple_secrets_without_returning_source_values() -> None:
    first = "synthetic_client_secret_Q7v9X2m4"
    second = "synthetic_runtime_token_Z8w1N5p3"
    service = SecretRedactionService(Settings())

    result = service.redact(
        f"client_secret={first}\nAuthorization: Bearer {second}",
        correlation_id="synthetic-correlation",
    )

    serialized = result.model_dump_json()
    assert result.redacted_text == (
        "client_secret=[REDACTED:GENERICSECRET]\n"
        "Authorization: Bearer [REDACTED:BEARERTOKEN]"
    )
    assert first not in serialized
    assert second not in serialized
    assert result.entity_counts == {"BearerToken": 1, "GenericSecret": 1}


def test_service_logs_only_safe_detection_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = "synthetic_client_secret_Q7v9X2m4"
    service = SecretRedactionService(Settings())

    with caplog.at_level(logging.INFO):
        service.redact(
            f"client_secret={value}",
            correlation_id="synthetic-correlation",
        )

    assert value not in caplog.text
    assert "GenericSecret" in caplog.text


class FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.state = SimpleNamespace(invocation_id="synthetic-invocation")

    async def body(self) -> bytes:
        return self._body


async def _stream_payload(response: Any) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        line = chunk.decode() if isinstance(chunk, bytes) else chunk
        for item in line.splitlines():
            if item.startswith("data: "):
                events.append(json.loads(item[6:]))
    return json.loads(events[-1]["full_text"])


@pytest.mark.asyncio
async def test_invocations_contract_redacts_secret() -> None:
    main = importlib.import_module("agents.secret_detection.main")
    value = "synthetic_client_secret_Q7v9X2m4"
    request = FakeRequest(
        json.dumps(
            {"contract_version": "1.0", "input": f"client_secret={value}"}
        ).encode()
    )

    response = await main.handle_invoke(request)
    payload = await _stream_payload(response)

    assert response.media_type == "text/event-stream"
    assert payload["contract_version"] == "1.0"
    assert payload["redacted_text"] == "client_secret=[REDACTED:GENERICSECRET]"
    assert value not in json.dumps(payload)


@pytest.mark.asyncio
async def test_invocations_contract_rejects_unknown_version() -> None:
    main = importlib.import_module("agents.secret_detection.main")

    response = await main.handle_invoke(
        FakeRequest(b'{"contract_version":"2.0","input":"synthetic"}')
    )

    assert response.status_code == 400
    assert b"invalid_request" in response.body


def test_hosted_agent_module_starts_server_when_executed() -> None:
    main = importlib.import_module("agents.secret_detection.main")

    source = inspect.getsource(main)

    assert 'if __name__ == "__main__":' in source
    assert "app.run()" in source
