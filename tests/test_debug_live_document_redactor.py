from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.debug_live_document_redactor import invoke_and_save, main
from scripts.live_agent_client import LiveAgentInvocationError


class StubClient:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.payload: dict[str, Any] | None = None

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = payload
        return self.result


def test_direct_script_loads_workspace_modules() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(  # noqa: S603 - trusted interpreter and script path.
        [
            sys.executable,
            str(repository_root / "scripts" / "debug_live_document_redactor.py"),
            "--help",
        ],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "--endpoint" in result.stdout


@pytest.mark.asyncio
async def test_invokes_pdf_once_and_saves_response_without_parsing(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.pdf"
    destination = tmp_path / "output" / source.name
    source.write_bytes(b"synthetic-pdf-input")
    returned = b"opaque-agent-response"
    client = StubClient(
        {"redacted_document_base64": base64.b64encode(returned).decode("ascii")}
    )

    result = await invoke_and_save(source, destination, client)

    assert result == destination
    assert destination.read_bytes() == returned
    assert client.payload is not None
    document = client.payload["document"]
    assert document["filename"] == source.name
    assert document["content_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_does_not_replace_output_when_agent_returns_no_document(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.pdf"
    destination = tmp_path / "output" / source.name
    source.write_bytes(b"synthetic-pdf-input")
    destination.parent.mkdir()
    destination.write_bytes(b"existing-output")

    with pytest.raises(RuntimeError, match="no redacted document"):
        await invoke_and_save(source, destination, StubClient({}))

    assert destination.read_bytes() == b"existing-output"


def test_main_reports_sanitized_live_invocation_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fail(_arguments: object) -> int:
        raise LiveAgentInvocationError(
            "Live hosted-agent invocation failed with HTTP 422 (processing_failed)"
        )

    monkeypatch.setattr("scripts.debug_live_document_redactor._run", fail)

    assert main([]) == 1
    output = capsys.readouterr().out
    assert "HTTP 422" in output
    assert "processing_failed" in output
    assert "https://" not in output


def test_main_uses_endpoint_from_selected_azd_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.pdf"
    destination = tmp_path / "redacted.pdf"
    source.write_bytes(b"synthetic-pdf-input")
    endpoints: list[str] = []

    class StubCredential:
        def close(self) -> None:
            pass

    class StubLiveAgentClient(StubClient):
        def __init__(
            self,
            endpoint: str,
            _credential: StubCredential,
            *,
            timeout_seconds: float,
        ) -> None:
            endpoints.append(endpoint)
            assert timeout_seconds == 240.0
            super().__init__(
                {
                    "redacted_document_base64": base64.b64encode(
                        b"synthetic-redacted-response"
                    ).decode("ascii")
                }
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
            stdout="https://synthetic.example.test/invocations\n",
            stderr="",
        )

    monkeypatch.delenv(
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
        raising=False,
    )
    monkeypatch.setattr(subprocess, "run", run_azd)
    monkeypatch.setattr(
        "scripts.debug_live_document_redactor.DefaultAzureCredential",
        lambda **_kwargs: StubCredential(),
    )
    monkeypatch.setattr(
        "scripts.debug_live_document_redactor.LiveAgentClient",
        StubLiveAgentClient,
    )

    assert main(
        [
            "--input",
            str(source),
            "--output",
            str(destination),
            "--timeout-seconds",
            "240",
        ]
    ) == 0
    assert endpoints == ["https://synthetic.example.test/invocations"]
    assert destination.read_bytes() == b"synthetic-redacted-response"