from __future__ import annotations

import subprocess

import pytest

from scripts import deploy_redaction_chat


def deployment_environment() -> dict[str, str]:
    return {
        name: f"synthetic-{name.lower()}"
        for name in deploy_redaction_chat.REQUIRED_VARIABLES
    }


def completed(
    returncode: int = 0, *, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)


def test_builds_and_configures_chat_without_printing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def run_az(
        arguments: tuple[str, ...], *, timeout: int = 120
    ) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        assert timeout == 1800
        return completed()

    monkeypatch.setattr(deploy_redaction_chat, "run_azure_cli", run_az)
    monkeypatch.setattr(deploy_redaction_chat, "wait_for_image", lambda *args: None)
    values = deployment_environment()

    deploy_redaction_chat.deploy_chat(values, image_tag="synthetic-tag")

    assert [command[:2] for command in commands] == [
        ("acr", "build"),
        ("containerapp", "registry"),
        ("containerapp", "ingress"),
        ("containerapp", "update"),
    ]
    assert "--no-logs" in commands[0]
    assert commands[0][-1] == str(deploy_redaction_chat.REPOSITORY_ROOT)
    assert str(deploy_redaction_chat.REPOSITORY_ROOT / "Dockerfile.web") in commands[0]
    assert "system" in commands[1]
    update = commands[3]
    assert any(item.endswith("/redaction-chat:synthetic-tag") for item in update)
    assert sum("INVOCATIONS_ENDPOINT=" in item for item in update) == 3


def test_reports_only_missing_variable_names() -> None:
    values = deployment_environment()
    values.pop("AZURE_REDACTION_CHAT_NAME")

    with pytest.raises(RuntimeError) as error:
        deploy_redaction_chat.deploy_chat(values, image_tag="synthetic-tag")

    assert str(error.value) == (
        "Missing azd environment variables: AZURE_REDACTION_CHAT_NAME"
    )


def test_uses_value_blind_failure_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        deploy_redaction_chat,
        "run_azure_cli",
        lambda arguments, *, timeout=120: completed(returncode=1),
    )

    with pytest.raises(RuntimeError) as error:
        deploy_redaction_chat.deploy_chat(
            deployment_environment(), image_tag="synthetic-tag"
        )

    assert str(error.value) == "Could not build image for the redaction chat"


def test_waits_until_built_image_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    results = iter((completed(returncode=1), completed()))
    sleeps: list[int] = []
    monkeypatch.setattr(
        deploy_redaction_chat, "run_azure_cli", lambda arguments: next(results)
    )
    monkeypatch.setattr(deploy_redaction_chat.time, "sleep", sleeps.append)

    deploy_redaction_chat.wait_for_image(
        "synthetic-registry", "redaction-chat:synthetic-tag", attempts=2
    )

    assert sleeps == [5]


def test_reports_missing_azure_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy_redaction_chat.shutil, "which", lambda command: None)

    with pytest.raises(RuntimeError, match="Azure CLI is required"):
        deploy_redaction_chat.run_azure_cli(("version",))


def test_runs_azure_cli_with_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    observed_environment: dict[str, str] = {}

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_environment.update(kwargs["env"])  # type: ignore[arg-type]
        return completed()

    monkeypatch.setattr(deploy_redaction_chat.shutil, "which", lambda command: "az")
    monkeypatch.setattr(deploy_redaction_chat.subprocess, "run", run)

    deploy_redaction_chat.run_azure_cli(("version",))

    assert observed_environment["PYTHONIOENCODING"] == "utf-8"
    assert observed_environment["PYTHONUTF8"] == "1"