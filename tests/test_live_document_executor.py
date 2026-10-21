from __future__ import annotations

import asyncio
import base64
import io
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter

from scripts.live_document_executor import (
    discover_input_files,
    execute,
    redact_file,
    resolve_endpoint,
)


class StubDocumentAgentClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.active_invocations = 0
        self.maximum_active_invocations = 0

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.active_invocations += 1
        self.maximum_active_invocations = max(
            self.maximum_active_invocations,
            self.active_invocations,
        )
        await asyncio.sleep(0)
        self.payloads.append(payload)
        document = payload["document"]
        assert isinstance(document, dict)
        content = base64.b64decode(document["content_base64"]).decode("utf-8")
        self.active_invocations -= 1
        return {"redacted_text": content.replace("synthetic.user@example.test", "[EMAIL]")}


class StubNativeDocumentAgentClient:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return {
            "redacted_document_base64": base64.b64encode(self.content).decode("ascii"),
        }


def valid_pdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def test_resolve_endpoint_prefers_explicit_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
        "https://environment.example.test/invocations",
    )

    endpoint = resolve_endpoint("https://explicit.example.test/invocations")

    assert endpoint == "https://explicit.example.test/invocations"


def test_resolve_endpoint_uses_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
        "https://environment.example.test/invocations",
    )

    assert resolve_endpoint() == "https://environment.example.test/invocations"


def test_resolve_endpoint_uses_selected_azd_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
        raising=False,
    )

    def run_azd(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert Path(command[0]).stem.casefold() == "azd"
        assert command[1:] == [
            "env",
            "get-value",
            "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
            "--no-prompt",
        ]
        assert kwargs["env"]["AZURE_DEV_USER_AGENT"] == "microsoft_foundry_skill"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="https://azd.example.test/invocations\n",
            stderr="",
        )

    monkeypatch.setattr("scripts.live_agent_client.shutil.which", lambda _: "azd")
    monkeypatch.setattr(subprocess, "run", run_azd)

    assert resolve_endpoint() == "https://azd.example.test/invocations"


def test_resolve_endpoint_reports_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
        raising=False,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            stdout="",
            stderr="synthetic azd failure",
        ),
    )

    with pytest.raises(ValueError, match="select an azd environment"):
        resolve_endpoint()


@pytest.mark.parametrize(
    "suffix",
    [".txt", ".csv", ".json", ".xml", ".md", ".log", ".docx", ".pdf"],
)
def test_discovers_supported_file_types(tmp_path: Path, suffix: str) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / f"synthetic{suffix}"
    source.write_text("synthetic", encoding="utf-8")

    assert discover_input_files(input_dir) == [source.resolve()]


@pytest.mark.asyncio
async def test_executor_processes_files_sequentially_with_same_names(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    expected_names = ["a.txt", "b.csv", "c.json"]
    for name in expected_names:
        (input_dir / name).write_text(
            "Contact synthetic.user@example.test",
            encoding="utf-8",
        )
    client = StubDocumentAgentClient()

    completed = await execute(input_dir, output_dir, client)

    assert completed == 3
    assert client.maximum_active_invocations == 1
    assert sorted(path.name for path in output_dir.iterdir()) == expected_names
    for name in expected_names:
        output = (output_dir / name).read_text(encoding="utf-8")
        assert output == "Contact [EMAIL]"
        assert "synthetic.user@example.test" not in output


@pytest.mark.asyncio
async def test_executor_can_process_one_selected_file(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "first.txt").write_text("first", encoding="utf-8")
    (input_dir / "second.txt").write_text("second", encoding="utf-8")
    client = StubDocumentAgentClient()

    completed = await execute(
        input_dir,
        output_dir,
        client,
        selected_file=Path("second.txt"),
    )

    assert completed == 1
    assert [path.name for path in output_dir.iterdir()] == ["second.txt"]
    assert len(client.payloads) == 1


@pytest.mark.asyncio
async def test_executor_preserves_native_document_bytes(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    output_dir = tmp_path / "output"
    source.write_bytes(valid_pdf())
    redacted = valid_pdf()

    destination = await redact_file(
        source,
        output_dir,
        StubNativeDocumentAgentClient(redacted),
        max_bytes=1024,
        overwrite=False,
    )

    assert destination.read_bytes() == redacted


@pytest.mark.asyncio
async def test_executor_rejects_invalid_pdf_without_replacing_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.pdf"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    source.write_bytes(valid_pdf())
    destination = output_dir / source.name
    destination.write_bytes(valid_pdf())
    original_output = destination.read_bytes()

    with pytest.raises(RuntimeError, match="invalid PDF artifact"):
        await redact_file(
            source,
            output_dir,
            StubNativeDocumentAgentClient(b"not-a-pdf"),
            max_bytes=1024 * 1024,
            overwrite=True,
        )

    assert destination.read_bytes() == original_output


@pytest.mark.asyncio
async def test_redact_file_refuses_to_overwrite_output(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.txt"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    source.write_text("synthetic", encoding="utf-8")
    (output_dir / source.name).write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="--overwrite"):
        await redact_file(
            source,
            output_dir,
            StubDocumentAgentClient(),
            max_bytes=1024,
            overwrite=False,
        )


def test_rejects_selected_file_outside_input_directory(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic", encoding="utf-8")

    with pytest.raises(ValueError, match="directly inside"):
        discover_input_files(input_dir, outside)


def test_rejects_unsupported_input_type(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "synthetic.exe").write_bytes(b"synthetic")

    with pytest.raises(ValueError, match="unsupported"):
        discover_input_files(input_dir)
