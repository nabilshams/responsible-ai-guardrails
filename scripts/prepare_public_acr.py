"""Remove legacy private ACR resources before migrating to Standard SKU."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence


def run_azure_cli(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("az")
    if executable is None:
        raise RuntimeError("Azure CLI is required to prepare the public registry")
    return subprocess.run(  # noqa: S603 - executable is resolved from PATH.
        [executable, *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
    )


def _resource_exists(resource_id: str, api_version: str) -> bool:
    result = run_azure_cli(
        ("resource", "show", "--ids", resource_id, "--api-version", api_version)
    )
    return result.returncode == 0


def _delete_resource(resource_id: str, api_version: str, description: str) -> None:
    if not _resource_exists(resource_id, api_version):
        return
    result = run_azure_cli(
        (
            "resource",
            "delete",
            "--ids",
            resource_id,
            "--api-version",
            api_version,
        )
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not remove the legacy {description}")


def prepare_public_acr(values: Mapping[str, str]) -> None:
    acr_id = values.get("AZURE_CONTAINER_REGISTRY_RESOURCE_ID", "").strip()
    subscription_id = values.get("AZURE_SUBSCRIPTION_ID", "").strip()
    resource_group = values.get("AZURE_RESOURCE_GROUP", "").strip()
    if not acr_id or not subscription_id or not resource_group:
        return

    resource_group_id = (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    )
    resources = (
        (
            f"{acr_id}/agentPools/privatebuild",
            "2019-06-01-preview",
            "ACR task agent pool",
        ),
        (
            f"{resource_group_id}/providers/Microsoft.Network/"
            "privateEndpoints/pe-acr",
            "2024-05-01",
            "ACR private endpoint",
        ),
        (
            f"{resource_group_id}/providers/Microsoft.Network/privateDnsZones/"
            "privatelink.azurecr.io/virtualNetworkLinks/acr-vnet-link",
            "2024-06-01",
            "ACR private DNS VNet link",
        ),
    )
    for resource_id, api_version, description in resources:
        _delete_resource(resource_id, api_version, description)


def main() -> None:
    prepare_public_acr(os.environ)
    print("Prepared Azure Container Registry for Standard public access.")


if __name__ == "__main__":
    main()