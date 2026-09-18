"""Build and configure the managed-identity redaction chat deployment."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_VARIABLES = (
    "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
    "AGENT_IMAGE_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
    "AGENT_PII_REDACTION_AGENT_INVOCATIONS_ENDPOINT",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT",
    "AZURE_CONTAINER_REGISTRY_NAME",
    "AZURE_ENV_NAME",
    "AZURE_REDACTION_CHAT_NAME",
    "AZURE_RESOURCE_GROUP",
)


def run_azure_cli(
    arguments: Sequence[str], *, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("az")
    if executable is None:
        raise RuntimeError("Azure CLI is required to deploy the redaction chat")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(  # noqa: S603 - executable is resolved from PATH; no shell.
        [executable, *arguments],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=timeout,
    )


def _require_values(values: Mapping[str, str]) -> dict[str, str]:
    missing = sorted(
        name for name in REQUIRED_VARIABLES if not values.get(name, "").strip()
    )
    if missing:
        raise RuntimeError("Missing azd environment variables: " + ", ".join(missing))
    return {name: values[name].strip() for name in REQUIRED_VARIABLES}


def wait_for_image(registry: str, image: str, *, attempts: int = 120) -> None:
    """Wait until a queued ACR build publishes its immutable image tag."""
    for attempt in range(attempts):
        result = run_azure_cli(
            (
                "acr",
                "repository",
                "show",
                "--name",
                registry,
                "--image",
                image,
                "--output",
                "none",
            )
        )
        if result.returncode == 0:
            return
        if attempt < attempts - 1:
            time.sleep(5)
    raise RuntimeError("Could not confirm the redaction chat image build")


def deploy_chat(values: Mapping[str, str], *, image_tag: str) -> None:
    """Build the image and update the app without displaying endpoint values."""
    required = _require_values(values)
    image = (
        f"{required['AZURE_CONTAINER_REGISTRY_ENDPOINT']}/"
        f"redaction-chat:{image_tag}"
    )
    commands = (
        (
            "build image",
            (
            "acr",
            "build",
            "--registry",
            required["AZURE_CONTAINER_REGISTRY_NAME"],
            "--image",
            f"redaction-chat:{image_tag}",
            "--file",
            str(REPOSITORY_ROOT / "Dockerfile.web"),
            "--no-logs",
            "--output",
            "none",
            str(REPOSITORY_ROOT),
            ),
        ),
        (
            "configure registry",
            (
            "containerapp",
            "registry",
            "set",
            "--name",
            required["AZURE_REDACTION_CHAT_NAME"],
            "--resource-group",
            required["AZURE_RESOURCE_GROUP"],
            "--server",
            required["AZURE_CONTAINER_REGISTRY_ENDPOINT"],
            "--identity",
            "system",
            "--output",
            "none",
            ),
        ),
        (
            "configure ingress",
            (
            "containerapp",
            "ingress",
            "update",
            "--name",
            required["AZURE_REDACTION_CHAT_NAME"],
            "--resource-group",
            required["AZURE_RESOURCE_GROUP"],
            "--target-port",
            "8000",
            "--output",
            "none",
            ),
        ),
        (
            "activate image",
            (
            "containerapp",
            "update",
            "--name",
            required["AZURE_REDACTION_CHAT_NAME"],
            "--resource-group",
            required["AZURE_RESOURCE_GROUP"],
            "--image",
            image,
            "--set-env-vars",
            "AGENT_PII_REDACTION_AGENT_INVOCATIONS_ENDPOINT="
            + required["AGENT_PII_REDACTION_AGENT_INVOCATIONS_ENDPOINT"],
            "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT="
            + required["AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT"],
            "AGENT_IMAGE_REDACTION_AGENT_INVOCATIONS_ENDPOINT="
            + required["AGENT_IMAGE_REDACTION_AGENT_INVOCATIONS_ENDPOINT"],
            "--output",
            "none",
            ),
        ),
    )
    for operation, command in commands:
        result = run_azure_cli(command, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(f"Could not {operation} for the redaction chat")
        if operation == "build image":
            wait_for_image(
                required["AZURE_CONTAINER_REGISTRY_NAME"],
                f"redaction-chat:{image_tag}",
            )


def main() -> None:
    image_tag = f"{os.environ.get('AZURE_ENV_NAME', 'azd')}-{datetime.now(UTC):%Y%m%d%H%M%S}"
    deploy_chat(os.environ, image_tag=image_tag)
    print("Built and configured the managed-identity redaction chat.")


if __name__ == "__main__":
    main()