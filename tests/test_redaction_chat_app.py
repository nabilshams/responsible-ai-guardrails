from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from scripts.redaction_chat_app import (
    AttachmentRequest,
    RedactionChatRequest,
    RedactionChatService,
    create_app,
)


class StubClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.payloads: list[dict[str, Any]] = []

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return self.response


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_routes_text_and_files_without_echoing_original_values() -> None:
    text_client = StubClient(
        {"redacted_text": "Contact [REDACTED:EMAIL]", "entity_counts": {"Email": 1}},
    )
    document_client = StubClient(
        {"redacted_text": "[REDACTED:EMAIL]", "entity_counts": {"Email": 1}},
    )
    image_client = StubClient(
        {
            "redacted_image_base64": base64.b64encode(_png()).decode("ascii"),
            "entity_counts": {"Email": 1},
        },
    )
    clients = {
        "AGENT_PII_REDACTION_AGENT_INVOCATIONS_ENDPOINT": text_client,
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT": document_client,
        "AGENT_IMAGE_REDACTION_AGENT_INVOCATIONS_ENDPOINT": image_client,
    }
    service = RedactionChatService(clients.__getitem__)
    request = RedactionChatRequest(
        message="Contact synthetic.user@example.test",
        files=[
            AttachmentRequest(
                name="private-customer.txt",
                content_base64=base64.b64encode(b"synthetic.user@example.test").decode(),
            ),
            AttachmentRequest(
                name="private-scan.jpg",
                content_base64=base64.b64encode(_png()).decode(),
            ),
        ],
    )

    response = await service.redact(request)
    serialized = response.model_dump_json()

    assert response.redacted_text == "Contact [REDACTED:EMAIL]"
    assert [item.download_name for item in response.files] == [
        "redacted-1.txt",
        "redacted-2.png",
    ]
    assert "synthetic.user@example.test" not in serialized
    assert "private-customer" not in serialized
    assert document_client.payloads[0]["document"]["filename"] == "upload-1.txt"
    assert image_client.payloads[0]["image"]["filename"] == "upload-2.jpg"


@pytest.mark.asyncio
async def test_rejects_unsupported_file_before_resolving_an_agent() -> None:
    service = RedactionChatService(lambda _: pytest.fail("agent should not be resolved"))
    request = RedactionChatRequest(
        files=[
            AttachmentRequest(
                name="synthetic.exe",
                content_base64=base64.b64encode(b"synthetic").decode(),
            ),
        ],
    )

    with pytest.raises(ValueError, match="not supported"):
        await service.redact(request)


@pytest.mark.asyncio
async def test_requires_text_or_files() -> None:
    service = RedactionChatService(lambda _: pytest.fail("agent should not be resolved"))

    with pytest.raises(ValueError, match="Provide text"):
        await service.redact(RedactionChatRequest())


def test_serves_chat_interface() -> None:
    response = TestClient(create_app(RedactionChatService(lambda _: StubClient({})))).get(
        "/",
    )

    assert response.status_code == 200
    assert 'id="composer"' in response.text
    assert 'id="sample-preview"' in response.text
    assert "Use this sample" in response.text
    assert 'fetch("/api/redact"' in response.text


def test_validation_error_does_not_echo_rejected_source_content() -> None:
    source = "synthetic.private@example.test"
    client = TestClient(create_app(RedactionChatService(lambda _: StubClient({}))))

    response = client.post(
        "/api/redact",
        json={"message": source, "language": "x", "files": []},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "The request format is invalid"}
    assert source not in response.text


def test_lists_ready_to_use_samples() -> None:
    client = TestClient(create_app(RedactionChatService(lambda _: StubClient({}))))

    response = client.get("/api/samples")

    assert response.status_code == 200
    samples = response.json()
    ids = {sample["id"] for sample in samples}
    assert {"text", "txt", "csv", "json", "docx", "pdf"} <= ids
    text_sample = next(sample for sample in samples if sample["id"] == "text")
    assert text_sample["kind"] == "text"
    assert text_sample["text"].strip()
    assert text_sample["previewable"] is False
    pdf_sample = next(sample for sample in samples if sample["id"] == "pdf")
    assert pdf_sample["previewable"] is True


def test_serves_a_named_sample_file() -> None:
    client = TestClient(create_app(RedactionChatService(lambda _: StubClient({}))))

    response = client.get("/api/samples/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content


def test_rejects_unknown_sample() -> None:
    client = TestClient(create_app(RedactionChatService(lambda _: StubClient({}))))

    response = client.get("/api/samples/does-not-exist")

    assert response.status_code == 404
