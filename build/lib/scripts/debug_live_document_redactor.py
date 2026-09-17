"""Invoke the live Document Redaction Agent once and save its document response."""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential

from scripts.live_agent_client import LiveAgentClient, LiveAgentInvocationError

_ENDPOINT_VARIABLE = "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT"
_DEFAULT_INPUT = Path("samples/input/synthetic-pii-form.pdf")
_DEFAULT_OUTPUT = Path("samples/output/synthetic-pii-form.pdf")
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


class DocumentAgentClient(Protocol):
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]: ...


async def invoke_and_save(
    source: Path,
    destination: Path,
    client: DocumentAgentClient,
    *,
    language: str = "en",
) -> Path:
    """Invoke once and atomically save returned bytes without parsing the document."""
    suffix = source.suffix.casefold()
    content_type = _CONTENT_TYPES.get(suffix)
    if content_type is None:
        raise ValueError("Debug runner supports only PDF, DOCX, and TXT files")
    if not source.is_file():
        raise ValueError("Input document does not exist")

    content = source.read_bytes()
    if not content:
        raise ValueError("Input document cannot be empty")

    result = await client.invoke(
        {
            "document": {
                "content_base64": base64.b64encode(content).decode("ascii"),
                "content_type": content_type,
                "filename": source.name,
            },
            "language": language,
        }
    )
    encoded = result.get("redacted_document_base64")
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("Live agent returned no redacted document")
    try:
        response_content = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RuntimeError("Live agent returned invalid base64 document data") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=".debug-redacted-",
            delete=False,
        ) as temporary:
            temporary.write(response_content)
            temporary_name = temporary.name
        Path(temporary_name).replace(destination)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Invoke the live Document Redaction Agent once and save its response "
            "without parsing the returned document."
        )
    )
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--endpoint", default=os.getenv(_ENDPOINT_VARIABLE, ""))
    parser.add_argument("--language", default="en")
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    return parser


async def _run(arguments: argparse.Namespace) -> int:
    if not arguments.endpoint:
        raise ValueError(f"Set {_ENDPOINT_VARIABLE} or pass --endpoint")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    try:
        client = LiveAgentClient(
            arguments.endpoint,
            credential,
            timeout_seconds=arguments.timeout_seconds,
        )
        destination = await invoke_and_save(
            arguments.input,
            arguments.output,
            client,
            language=arguments.language,
        )
    finally:
        credential.close()
    print(f"Saved live agent response to {destination}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the single-document live debug invocation."""
    try:
        return asyncio.run(_run(_parser().parse_args(argv)))
    except LiveAgentInvocationError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())