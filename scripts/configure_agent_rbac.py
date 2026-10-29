"""Assign least-privilege Azure RBAC to deployed hosted-agent identities."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleAssignment:
    """One runtime identity, resource scope, and built-in role binding."""

    agent: str
    principal_variable: str
    scope_variable: str
    role: str


ROLE_ASSIGNMENTS = (
    RoleAssignment(
        "PII Redaction Agent",
        "AGENT_PII_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID",
        "AZURE_AI_LANGUAGE_RESOURCE_ID",
        "Cognitive Services User",
    ),
    RoleAssignment(
        "Document Redaction Agent",
        "AGENT_DOCUMENT_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID",
        "AZURE_AI_LANGUAGE_RESOURCE_ID",
        "Cognitive Services User",
    ),
    RoleAssignment(
        "Document Redaction Agent",
        "AGENT_DOCUMENT_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID",
        "AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID",
        "Storage Blob Data Contributor",
    ),
    RoleAssignment(
        "Image Redaction Agent",
        "AGENT_IMAGE_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID",
        "AZURE_AI_LANGUAGE_RESOURCE_ID",
        "Cognitive Services User",
    ),
    RoleAssignment(
        "Image Redaction Agent",
        "AGENT_IMAGE_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID",
        "AZURE_DOCUMENT_INTELLIGENCE_RESOURCE_ID",
        "Cognitive Services User",
    ),
    RoleAssignment(
        "Redaction Chat",
        "AZURE_REDACTION_CHAT_PRINCIPAL_ID",
        "AZURE_AI_PROJECT_ID",
        "Foundry User",
    ),
)

AGENT_PRINCIPAL_LOOKUPS = {
    "AGENT_PII_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID": (
        "pii-redaction-agent"
    ),
    "AGENT_DOCUMENT_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID": (
        "document-redaction-agent"
    ),
    "AGENT_IMAGE_REDACTION_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID": (
        "image-redaction-agent"
    ),
}


def run_azure_cli(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("az")
    if executable is None:
        raise RuntimeError("Azure CLI is required to configure hosted-agent RBAC")
    return subprocess.run(  # noqa: S603 - executable is resolved from PATH; no shell.
        [executable, *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )


def run_azd_cli(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("azd")
    if executable is None:
        raise RuntimeError("Azure Developer CLI is required to inspect hosted agents")
    environment = os.environ.copy()
    environment["AZURE_DEV_USER_AGENT"] = "microsoft_foundry_skill"
    return subprocess.run(  # noqa: S603 - executable is resolved from PATH; no shell.
        [executable, *arguments],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=120,
    )


def resolve_agent_principals(values: Mapping[str, str]) -> dict[str, str]:
    """Resolve identity IDs omitted by concurrent azd agent deployments."""
    resolved = dict(values)
    for variable, service in AGENT_PRINCIPAL_LOOKUPS.items():
        if resolved.get(variable, "").strip():
            continue
        result = run_azd_cli(("ai", "agent", "show", service, "--output", "json"))
        if result.returncode != 0:
            raise RuntimeError(f"Could not inspect {service} runtime identity")
        try:
            principal = json.loads(result.stdout)["instance_identity"]["principal_id"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise RuntimeError(
                f"Could not resolve {service} runtime identity"
            ) from error
        if not isinstance(principal, str) or not principal.strip():
            raise RuntimeError(f"Could not resolve {service} runtime identity")
        resolved[variable] = principal.strip()
    return resolved


def configure_assignments(values: Mapping[str, str]) -> int:
    """Create missing assignments and return their count without exposing IDs."""
    resolved = resolve_agent_principals(values)
    required = {
        variable
        for assignment in ROLE_ASSIGNMENTS
        for variable in (assignment.principal_variable, assignment.scope_variable)
    }
    missing = sorted(name for name in required if not resolved.get(name, "").strip())
    if missing:
        raise RuntimeError("Missing azd environment variables: " + ", ".join(missing))

    created = 0
    for assignment in ROLE_ASSIGNMENTS:
        principal = resolved[assignment.principal_variable]
        scope = resolved[assignment.scope_variable]
        existing = run_azure_cli(
            (
                "role",
                "assignment",
                "list",
                "--assignee-object-id",
                principal,
                "--scope",
                scope,
                "--query",
                f"[?roleDefinitionName=='{assignment.role}'].id",
                "--output",
                "tsv",
            )
        )
        if existing.returncode != 0:
            raise RuntimeError(
                f"Could not inspect {assignment.role} for {assignment.agent}"
            )
        if existing.stdout.strip():
            continue

        result = run_azure_cli(
            (
                "role",
                "assignment",
                "create",
                "--assignee-object-id",
                principal,
                "--assignee-principal-type",
                "ServicePrincipal",
                "--role",
                assignment.role,
                "--scope",
                scope,
                "--output",
                "none",
            )
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Could not assign {assignment.role} to {assignment.agent}"
            )
        created += 1
    return created


def main() -> None:
    """Configure hosted-agent RBAC from values exported by ``azd up``."""
    created = configure_assignments(os.environ)
    print(f"Validated hosted-agent RBAC; created {created} missing assignment(s).")


if __name__ == "__main__":
    main()