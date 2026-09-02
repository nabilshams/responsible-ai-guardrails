"""Opt-in smoke tests against deployed Microsoft Foundry hosted agents.

All fixtures are synthetic. Enable with RUN_LIVE_AGENT_TESTS=1 after exporting each
deployed specialist's full Invocations endpoint and authenticating with Azure CLI or
another DefaultAzureCredential source.
"""

from __future__ import annotations

import base64
import io
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from azure.identity import DefaultAzureCredential
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from scripts.live_agent_client import LiveAgentClient

pytestmark = pytest.mark.azure

_SYNTHETIC_EMAIL = "synthetic.user@example.test"
_RUN_LIVE = os.getenv("RUN_LIVE_AGENT_TESTS", "").casefold() in {"1", "true", "yes"}


@dataclass(frozen=True, slots=True)
class SyntheticDocument:
    filename: str
    content_type: str
    content: bytes


def _agent_endpoint(variable: str, specialist: str) -> str:
    endpoint = os.getenv(variable, "").strip()
    if not endpoint.startswith("https://"):
        pytest.skip(
            f"{specialist} is not configured; set {variable} to its deployed "
            "Invocations endpoint"
        )
    return endpoint


@pytest_asyncio.fixture(scope="module", name="live_connection")
async def _live_connection() -> AsyncIterator[tuple[DefaultAzureCredential, float]]:
    if not _RUN_LIVE:
        pytest.skip("Set RUN_LIVE_AGENT_TESTS=1 to invoke deployed agents")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    try:
        yield (
            credential,
            float(os.getenv("LIVE_AGENT_TIMEOUT_SECONDS", "180")),
        )
    finally:
        credential.close()


def _document_payload(document: SyntheticDocument) -> dict[str, object]:
    return {
        "document": {
            "content_base64": base64.b64encode(document.content).decode("ascii"),
            "content_type": document.content_type,
            "filename": document.filename,
        },
        "language": "en",
    }


def _assert_email_redacted(result: dict[str, object]) -> None:
    redacted_text = result.get("redacted_text")
    assert isinstance(redacted_text, str)
    assert _SYNTHETIC_EMAIL not in redacted_text.casefold()
    assert "[REDACTED:" in redacted_text

    entity_counts = result.get("entity_counts")
    assert isinstance(entity_counts, dict)
    assert sum(value for value in entity_counts.values() if isinstance(value, int)) >= 1


def _assert_native_document_redacted(
    result: dict[str, object],
    source: SyntheticDocument,
) -> None:
    encoded = result.get("redacted_document_base64")
    assert isinstance(encoded, str)
    redacted = base64.b64decode(encoded, validate=True)
    assert redacted
    assert redacted != source.content
    assert result.get("content_type") == source.content_type
    if source.filename.endswith(".txt"):
        assert _SYNTHETIC_EMAIL.encode() not in redacted.lower()
    if source.filename.endswith(".pdf"):
        source_pdf = PdfReader(io.BytesIO(source.content), strict=True)
        redacted_pdf = PdfReader(io.BytesIO(redacted), strict=True)
        assert len(redacted_pdf.pages) == len(source_pdf.pages) > 0
        for source_page, redacted_page in zip(
            source_pdf.pages,
            redacted_pdf.pages,
            strict=True,
        ):
            assert redacted_page.mediabox.width == source_page.mediabox.width
            assert redacted_page.mediabox.height == source_page.mediabox.height


def _synthetic_pdf() -> bytes:
    image = Image.new("RGB", (1500, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=58)
    draw.text((50, 90), f"Synthetic email: {_SYNTHETIC_EMAIL}", fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PDF", resolution=150.0)
    return output.getvalue()


def _synthetic_png() -> bytes:
    image = Image.new("RGB", (1500, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=58)
    draw.text((50, 90), f"Synthetic email: {_SYNTHETIC_EMAIL}", fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_live_pii_agent_redacts_synthetic_text(
    live_connection: tuple[DefaultAzureCredential, float],
) -> None:
    credential, timeout = live_connection
    client = LiveAgentClient(
        _agent_endpoint(
            "AGENT_PII_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
            "PII Redaction Agent",
        ),
        credential,
        timeout_seconds=timeout,
    )
    result = await client.invoke(
        {"input": f"Synthetic contact: {_SYNTHETIC_EMAIL}", "language": "en"},
    )
    _assert_email_redacted(result)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param(
            SyntheticDocument(
                "synthetic.txt",
                "text/plain",
                f"Synthetic email: {_SYNTHETIC_EMAIL}".encode(),
            ),
            id="txt",
        ),
        pytest.param(
            SyntheticDocument(
                "synthetic.csv",
                "text/csv",
                f"kind,value\nsynthetic-email,{_SYNTHETIC_EMAIL}\n".encode(),
            ),
            id="csv",
        ),
        pytest.param(
            SyntheticDocument(
                "synthetic.json",
                "application/json",
                ('{"kind":"synthetic-email","value":"' + _SYNTHETIC_EMAIL + '"}').encode(),
            ),
            id="json",
        ),
        pytest.param(
            SyntheticDocument(
                "synthetic.xml",
                "application/xml",
                f"<synthetic><email>{_SYNTHETIC_EMAIL}</email></synthetic>".encode(),
            ),
            id="xml",
        ),
        pytest.param(
            SyntheticDocument(
                "synthetic.md",
                "text/markdown",
                f"# Synthetic contact\n\nEmail: {_SYNTHETIC_EMAIL}\n".encode(),
            ),
            id="markdown",
        ),
        pytest.param(
            SyntheticDocument(
                "synthetic.log",
                "application/octet-stream",
                f"level=info synthetic_email={_SYNTHETIC_EMAIL}\n".encode(),
            ),
            id="log",
        ),
        pytest.param(
            SyntheticDocument("synthetic.pdf", "application/pdf", b""),
            id="pdf",
        ),
    ],
)
@pytest.mark.asyncio
async def test_live_document_agent_redacts_each_supported_document(
    live_connection: tuple[DefaultAzureCredential, float],
    document: SyntheticDocument,
) -> None:
    if document.filename.endswith(".pdf"):
        document = SyntheticDocument(
            document.filename,
            document.content_type,
            _synthetic_pdf(),
        )
    credential, timeout = live_connection
    client = LiveAgentClient(
        _agent_endpoint(
            "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
            "Document Redaction Agent",
        ),
        credential,
        timeout_seconds=timeout,
    )
    result = await client.invoke(
        _document_payload(document),
    )
    if document.filename.endswith((".txt", ".pdf", ".docx")):
        _assert_native_document_redacted(result, document)
    else:
        _assert_email_redacted(result)


@pytest.mark.asyncio
async def test_live_image_agent_masks_synthetic_pii(
    live_connection: tuple[DefaultAzureCredential, float],
) -> None:
    source = _synthetic_png()
    credential, timeout = live_connection
    client = LiveAgentClient(
        _agent_endpoint(
            "AGENT_IMAGE_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
            "Image Redaction Agent",
        ),
        credential,
        timeout_seconds=timeout,
    )
    result = await client.invoke(
        {
            "image": {
                "content_base64": base64.b64encode(source).decode("ascii"),
                "content_type": "image/png",
                "filename": "synthetic.png",
            },
            "language": "en",
        },
    )

    _assert_email_redacted(result)
    encoded = result.get("redacted_image_base64")
    assert isinstance(encoded, str)
    redacted = base64.b64decode(encoded, validate=True)
    assert redacted != source
    with Image.open(io.BytesIO(redacted)) as image:
        assert image.format == "PNG"
        assert image.size == (1500, 300)
