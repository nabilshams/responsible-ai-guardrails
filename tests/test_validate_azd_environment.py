from __future__ import annotations

from scripts.validate_azd_environment import (
    _AGENT_SERVICES,
    _REQUIRED_VARIABLES,
    find_missing_variables,
)


def complete_environment(*, use_vnet: bool) -> dict[str, str]:
    values = {name: "synthetic-value" for name in _REQUIRED_VARIABLES}
    values["USE_VNET"] = str(use_vnet).lower()
    for service in _AGENT_SERVICES:
        values[f"AGENT_{service}_ENDPOINT"] = "https://synthetic.example.test"
        values[f"AGENT_{service}_INSTANCE_IDENTITY_CLIENT_ID"] = "synthetic-client-id"
        values[f"AGENT_{service}_INSTANCE_IDENTITY_PRINCIPAL_ID"] = (
            "synthetic-principal-id"
        )
        values[f"AGENT_{service}_NAME"] = "synthetic-agent"
        values[f"AGENT_{service}_PROJECT_ENDPOINT"] = (
            "https://synthetic.example.test/project"
        )
        values[f"AGENT_{service}_INVOCATIONS_ENDPOINT"] = (
            "https://synthetic.example.test/invocations"
        )
    if use_vnet:
        values.update(
            VNET_ID="synthetic-vnet-id",
            AGENT_SUBNET_ID="synthetic-agent-subnet-id",
            PE_SUBNET_ID="synthetic-private-endpoint-subnet-id",
            WEB_SUBNET_ID="synthetic-web-subnet-id",
        )
    return values


def test_complete_public_environment_does_not_require_network_resource_ids() -> None:
    assert find_missing_variables(complete_environment(use_vnet=False)) == []


def test_speech_endpoint_is_required() -> None:
    values = complete_environment(use_vnet=False)
    values.pop("AZURE_SPEECH_ENDPOINT")

    assert find_missing_variables(values) == ["AZURE_SPEECH_ENDPOINT"]


def test_complete_private_environment_requires_network_resource_ids() -> None:
    values = complete_environment(use_vnet=True)
    values["AGENT_SUBNET_ID"] = ""

    assert find_missing_variables(values) == ["AGENT_SUBNET_ID"]


def test_private_environment_requires_web_subnet_id() -> None:
    values = complete_environment(use_vnet=True)
    values["WEB_SUBNET_ID"] = ""

    assert find_missing_variables(values) == ["WEB_SUBNET_ID"]


def test_reports_missing_agent_deploy_output_by_name_only() -> None:
    values = complete_environment(use_vnet=False)
    values.pop("AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT")

    assert find_missing_variables(values) == [
        "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT"
    ]


def test_agent_version_metadata_is_optional() -> None:
    values = complete_environment(use_vnet=False)
    values["AGENT_PII_REDACTION_AGENT_VERSION"] = ""

    assert find_missing_variables(values) == []