"""Validate the value-blind environment contract produced by ``azd up``."""

from __future__ import annotations

import os
from collections.abc import Mapping

_REQUIRED_VARIABLES = (
    "AZURE_ENV_NAME",
    "AZURE_LOCATION",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_TENANT_ID",
    "USE_VNET",
    "VNET_ADDRESS_PREFIX",
    "AGENT_SUBNET_PREFIX",
    "PE_SUBNET_PREFIX",
    "AI_LANGUAGE_SKU",
    "DOCUMENT_INTELLIGENCE_SKU",
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_PROJECT_ENDPOINT",
    "AZURE_AIPROJECT_ENDPOINT",
    "AZURE_AI_PROJECT_ID",
    "AZURE_AI_PROJECT_NAME",
    "AZURE_AI_ACCOUNT_NAME",
    "AZURE_AI_AISERVICES_ACCOUNT_NAME",
    "AZURE_AI_LANGUAGE_ENDPOINT",
    "AZURE_AI_LANGUAGE_RESOURCE_ID",
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_RESOURCE_ID",
    "AZURE_DOCUMENT_PII_STORAGE_ENDPOINT",
    "AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID",
    "AZURE_DOCUMENT_PII_SOURCE_CONTAINER",
    "AZURE_DOCUMENT_PII_TARGET_CONTAINER",
    "AZURE_CONTAINER_REGISTRY_RESOURCE_ID",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT",
    "AZURE_CONTAINER_REGISTRY_NAME",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AZURE_LOG_ANALYTICS_WORKSPACE_ID",
    "AZURE_RESOURCE_GROUP",
    "ENABLE_CAPABILITY_HOST",
    "PII_CONFIDENCE_THRESHOLD",
    "PII_DEFAULT_LANGUAGE",
)

_AGENT_SERVICES = (
    "PII_REDACTION_AGENT",
    "DOCUMENT_REDACTION_AGENT",
    "IMAGE_REDACTION_AGENT",
)


def find_missing_variables(values: Mapping[str, str]) -> list[str]:
    """Return missing names without inspecting or exposing populated values."""
    required = list(_REQUIRED_VARIABLES)
    for service in _AGENT_SERVICES:
        required.extend(
            (
                f"AGENT_{service}_ENDPOINT",
                f"AGENT_{service}_INSTANCE_IDENTITY_CLIENT_ID",
                f"AGENT_{service}_INSTANCE_IDENTITY_PRINCIPAL_ID",
                f"AGENT_{service}_NAME",
                f"AGENT_{service}_PROJECT_ENDPOINT",
                f"AGENT_{service}_VERSION",
                f"AGENT_{service}_INVOCATIONS_ENDPOINT",
            )
        )

    use_vnet = values.get("USE_VNET", "").strip().lower() == "true"
    if use_vnet:
        required.extend(("VNET_ID", "AGENT_SUBNET_ID", "PE_SUBNET_ID"))

    return sorted(name for name in required if not values.get(name, "").strip())


def main() -> None:
    """Fail the azd workflow when its promised environment contract is incomplete."""
    missing = find_missing_variables(os.environ)
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"azd up did not populate required environment variables: {names}")

    print("Validated azd environment variable names; values were not displayed.")


if __name__ == "__main__":
    main()