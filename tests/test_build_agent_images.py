from __future__ import annotations

import subprocess

import pytest

from scripts import build_agent_images


def completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr="")


def test_builds_each_agent_with_standard_acr_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(build_agent_images, "image_exists", lambda *args: False)
    monkeypatch.setattr(
        build_agent_images,
        "run_azure_cli",
        lambda arguments, *, timeout=1800: commands.append(tuple(arguments))
        or completed(),
    )
    monkeypatch.setattr(
        build_agent_images, "wait_for_image", lambda *args: None
    )

    build_agent_images.build_agent_images(
        {
            "AZURE_CONTAINER_REGISTRY_NAME": "synthetic-registry",
            "AZURE_ENV_NAME": "synthetic-tag",
        }
    )

    assert len(commands) == 3
    assert all("--agent-pool" not in command for command in commands)
    assert all("--no-logs" in command for command in commands)
    assert all(
        command[-1] == str(build_agent_images.REPOSITORY_ROOT)
        for command in commands
    )


def test_skips_agent_images_that_already_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_agent_images, "image_exists", lambda *args: True)
    monkeypatch.setattr(
        build_agent_images,
        "run_azure_cli",
        lambda *args, **kwargs: pytest.fail("existing images must not be rebuilt"),
    )

    build_agent_images.build_agent_images(
        {
            "AZURE_CONTAINER_REGISTRY_NAME": "synthetic-registry",
            "AZURE_ENV_NAME": "synthetic-tag",
        }
    )


def test_reports_only_missing_environment_variable_names() -> None:
    with pytest.raises(RuntimeError) as error:
        build_agent_images.build_agent_images({})

    assert str(error.value) == (
        "Missing azd environment variables: "
        "AZURE_CONTAINER_REGISTRY_NAME, AZURE_ENV_NAME"
    )


def test_uses_value_blind_build_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_agent_images, "image_exists", lambda *args: False)
    monkeypatch.setattr(
        build_agent_images,
        "run_azure_cli",
        lambda arguments, *, timeout=1800: completed(returncode=1),
    )

    with pytest.raises(RuntimeError) as error:
        build_agent_images.build_agent_images(
            {
                "AZURE_CONTAINER_REGISTRY_NAME": "synthetic-registry",
                "AZURE_ENV_NAME": "synthetic-tag",
            }
        )

    assert str(error.value) == "Could not build the pii-redaction-agent image"