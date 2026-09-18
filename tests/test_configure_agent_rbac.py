from __future__ import annotations

import subprocess

import pytest

from scripts import configure_agent_rbac


def assignment_environment() -> dict[str, str]:
    return {
        variable: "synthetic-id"
        for assignment in configure_agent_rbac.ROLE_ASSIGNMENTS
        for variable in (assignment.principal_variable, assignment.scope_variable)
    }


def completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def test_creates_each_missing_assignment(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []

    def run_az(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        return completed()

    monkeypatch.setattr(configure_agent_rbac, "run_azure_cli", run_az)

    created = configure_agent_rbac.configure_assignments(assignment_environment())

    assert created == len(configure_agent_rbac.ROLE_ASSIGNMENTS)
    assert sum(command[2] == "create" for command in commands) == created
    assert any(
        "Foundry User" in command
        and "AZURE_AI_PROJECT_ID" not in command
        and "synthetic-id" in command
        for command in commands
        if command[2] == "create"
    )


def test_skips_existing_assignments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        configure_agent_rbac,
        "run_azure_cli",
        lambda arguments: completed("synthetic-assignment-id\n"),
    )

    assert configure_agent_rbac.configure_assignments(assignment_environment()) == 0


def test_reports_only_missing_variable_names() -> None:
    values = assignment_environment()
    values.pop("AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID")

    with pytest.raises(RuntimeError) as error:
        configure_agent_rbac.configure_assignments(values)

    assert str(error.value) == (
        "Missing azd environment variables: AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID"
    )


def test_reports_missing_azure_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(configure_agent_rbac.shutil, "which", lambda command: None)

    with pytest.raises(RuntimeError, match="Azure CLI is required"):
        configure_agent_rbac.run_azure_cli(("version",))