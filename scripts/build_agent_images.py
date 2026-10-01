"""Build hosted-agent images with standard Azure Container Registry tasks."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_VARIABLES = (
    "AZURE_CONTAINER_REGISTRY_NAME",
    "AZURE_ENV_NAME",
)
AGENT_IMAGES = (
    ("pii-redaction-agent", "agents.pii_redaction.main"),
    ("secret-detection-agent", "agents.secret_detection.main"),
    ("document-redaction-agent", "agents.document_redaction.main"),
    ("image-redaction-agent", "agents.image_redaction.main"),
)


def run_azure_cli(
    arguments: Sequence[str], *, timeout: int = 1800
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("az")
    if executable is None:
        raise RuntimeError("Azure CLI is required to build hosted-agent images")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(  # noqa: S603 - executable is resolved from PATH.
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


def image_exists(registry: str, image: str) -> bool:
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
    return result.returncode == 0


def wait_for_image(registry: str, image: str, *, attempts: int = 120) -> None:
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
    raise RuntimeError("Could not confirm a hosted-agent image build")


def build_agent_images(values: Mapping[str, str]) -> None:
    required = _require_values(values)
    registry = required["AZURE_CONTAINER_REGISTRY_NAME"]
    image_tag = required["AZURE_ENV_NAME"]

    for image_name, agent_module in AGENT_IMAGES:
        image = f"{image_name}:{image_tag}"
        if image_exists(registry, image):
            continue
        result = run_azure_cli(
            (
                "acr",
                "build",
                "--registry",
                registry,
                "--image",
                image,
                "--file",
                str(REPOSITORY_ROOT / "Dockerfile"),
                "--build-arg",
                f"AGENT_MODULE={agent_module}",
                "--no-logs",
                "--output",
                "none",
                str(REPOSITORY_ROOT),
            )
        )
        if result.returncode != 0:
            raise RuntimeError(f"Could not build the {image_name} image")
        wait_for_image(registry, image)


def main() -> None:
    build_agent_images(os.environ)
    print("Built hosted-agent images with standard Azure Container Registry tasks.")


if __name__ == "__main__":
    main()