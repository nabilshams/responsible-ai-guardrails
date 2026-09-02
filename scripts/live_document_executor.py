"""Sequentially redact sample files with the live Document Redaction Agent."""

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

from scripts.live_agent_client import LiveAgentClient
from shared.guardrails.native_document_pii import validate_native_document

_SUPPORTED_TYPES = {
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".md": "text/markdown",
    ".log": "application/octet-stream",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
_DEFAULT_INPUT = Path("samples/input")
_DEFAULT_OUTPUT = Path("samples/output")
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_ENDPOINT_VARIABLE = "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT"


class DocumentAgentClient(Protocol):
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def discover_input_files(input_dir: Path, selected_file: Path | None = None) -> list[Path]:
    """Return supported files in deterministic order without descending directories."""
    input_dir = input_dir.resolve()
    if selected_file is not None:
        candidate = selected_file if selected_file.is_absolute() else input_dir / selected_file
        candidate = candidate.resolve()
        if candidate.parent != input_dir:
            raise ValueError("The selected file must be directly inside the input directory")
        candidates = [candidate]
    else:
        candidates = sorted(path for path in input_dir.iterdir() if path.is_file())

    unsupported = [path for path in candidates if path.suffix.casefold() not in _SUPPORTED_TYPES]
    if unsupported:
        raise ValueError("The input folder contains an unsupported file type")
    if not candidates:
        raise ValueError("The input folder contains no supported files")
    return candidates


async def redact_file(
    source: Path,
    output_dir: Path,
    client: DocumentAgentClient,
    *,
    max_bytes: int,
    overwrite: bool,
) -> Path:
    """Invoke the live agent for one file and atomically save redacted text."""
    size = source.stat().st_size
    if size == 0:
        raise ValueError("Input files cannot be empty")
    if size > max_bytes:
        raise ValueError("An input file exceeds the configured size limit")

    suffix = source.suffix.casefold()
    content_type = _SUPPORTED_TYPES.get(suffix)
    if content_type is None:
        raise ValueError("The input file type is not supported")

    destination = output_dir.resolve() / source.name
    if destination.exists() and not overwrite:
        raise FileExistsError("An output file already exists; use --overwrite to replace it")

    payload = {
        "document": {
            "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
            "content_type": content_type,
            "filename": source.name,
        },
        "language": "en",
    }
    result = await client.invoke(payload)
    encoded_document = result.get("redacted_document_base64")
    redacted_text = result.get("redacted_text")
    if isinstance(encoded_document, str):
        try:
            decoded_document = base64.b64decode(encoded_document, validate=True)
        except ValueError as exc:
            raise RuntimeError("The live agent returned an invalid redacted document") from exc
        validate_native_document(decoded_document, suffix)
        output_content: bytes | str = decoded_document
        output_mode = "wb"
        output_encoding = None
    elif isinstance(redacted_text, str):
        output_content = redacted_text
        output_mode = "w"
        output_encoding = "utf-8"
    else:
        raise RuntimeError("The live agent returned no redacted content")

    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode=output_mode,
            encoding=output_encoding,
            newline="" if output_mode == "w" else None,
            dir=output_dir,
            prefix=".redacted-",
            delete=False,
        ) as temporary:
            temporary.write(output_content)
            temporary_name = temporary.name
        Path(temporary_name).replace(destination)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return destination


async def execute(
    input_dir: Path,
    output_dir: Path,
    client: DocumentAgentClient,
    *,
    selected_file: Path | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    overwrite: bool = False,
) -> int:
    """Process files sequentially and return the completed file count."""
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("Input and output directories must be different")
    files = discover_input_files(input_dir, selected_file)
    completed = 0
    for source in files:
        await redact_file(
            source,
            output_dir,
            client,
            max_bytes=max_bytes,
            overwrite=overwrite,
        )
        completed += 1
    return completed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send sample documents to the live Document Redaction Agent sequentially.",
    )
    parser.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--file",
        type=Path,
        help="Process only this file from the input directory; otherwise process all files.",
    )
    parser.add_argument("--endpoint", default=os.getenv(_ENDPOINT_VARIABLE, ""))
    parser.add_argument("--max-bytes", type=int, default=_DEFAULT_MAX_BYTES)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--overwrite", action="store_true")
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
        completed = await execute(
            arguments.input_dir,
            arguments.output_dir,
            client,
            selected_file=arguments.file,
            max_bytes=arguments.max_bytes,
            overwrite=arguments.overwrite,
        )
    finally:
        credential.close()
    print(f"Successfully redacted {completed} file(s).")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line executor."""
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
