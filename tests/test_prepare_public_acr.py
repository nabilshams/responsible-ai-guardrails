from __future__ import annotations

import subprocess

import pytest

from scripts import prepare_public_acr


def completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr="")


def migration_environment() -> dict[str, str]:
    return {
        "AZURE_CONTAINER_REGISTRY_RESOURCE_ID": (
            "/subscriptions/synthetic-subscription/resourceGroups/synthetic-rg/"
            "providers/Microsoft.ContainerRegistry/registries/synthetic-registry"
        ),
        "AZURE_SUBSCRIPTION_ID": "synthetic-subscription",
        "AZURE_RESOURCE_GROUP": "synthetic-rg",
    }


def test_removes_legacy_private_acr_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def run_az(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        return completed()

    monkeypatch.setattr(prepare_public_acr, "run_azure_cli", run_az)

    prepare_public_acr.prepare_public_acr(migration_environment())

    delete_commands = [command for command in commands if command[1] == "delete"]
    assert len(delete_commands) == 3
    assert any("agentPools/privatebuild" in command[3] for command in delete_commands)
    assert any("privateEndpoints/pe-acr" in command[3] for command in delete_commands)
    assert any("acr-vnet-link" in command[3] for command in delete_commands)


def test_fresh_environment_requires_no_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prepare_public_acr,
        "run_azure_cli",
        lambda arguments: pytest.fail("Azure CLI should not run"),
    )

    prepare_public_acr.prepare_public_acr({})


def test_cleanup_failure_is_value_blind(monkeypatch: pytest.MonkeyPatch) -> None:
    results = iter((completed(), completed(returncode=1)))
    monkeypatch.setattr(
        prepare_public_acr, "run_azure_cli", lambda arguments: next(results)
    )

    with pytest.raises(RuntimeError) as error:
        prepare_public_acr.prepare_public_acr(migration_environment())

    assert str(error.value) == "Could not remove the legacy ACR task agent pool"