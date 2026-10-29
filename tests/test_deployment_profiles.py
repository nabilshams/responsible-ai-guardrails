from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INFRA_ROOT = REPOSITORY_ROOT / "infra"


def test_private_profile_enables_public_foundry_with_private_dependencies() -> None:
    entrypoint = (INFRA_ROOT / "private" / "main.bicep").read_text(encoding="utf-8")
    ai_module = (INFRA_ROOT / "modules" / "ai.bicep").read_text(encoding="utf-8")

    assert "useVnet: true" in entrypoint
    assert "allowPublicFoundryAccess: true" in entrypoint
    assert "(!useVnet || allowPublicFoundryAccess) ? 'Enabled' : 'Disabled'" in ai_module
    assert "(!useVnet || allowPublicFoundryAccess) ? 'Allow' : 'Deny'" in ai_module
    assert "var publicNetworkAccess = useVnet ? 'Disabled' : 'Enabled'" in ai_module
    assert "var networkDefaultAction = useVnet ? 'Deny' : 'Allow'" in ai_module


def test_all_profiles_use_standard_public_acr() -> None:
    acr_module = (INFRA_ROOT / "modules" / "acr.bicep").read_text(encoding="utf-8")
    orchestration = (INFRA_ROOT / "main.bicep").read_text(encoding="utf-8")
    acr_connection = (
        INFRA_ROOT / "modules" / "foundryAcrConnection.bicep"
    ).read_text(encoding="utf-8")
    private_endpoints = (INFRA_ROOT / "modules" / "privateEndpoints.bicep").read_text(
        encoding="utf-8"
    )

    assert "name: 'Standard'" in acr_module
    assert "publicNetworkAccess: 'Enabled'" in acr_module
    assert "adminUserEnabled: false" in acr_module
    assert "acrAgentPool" not in orchestration
    assert "acrPrivateEndpoint" not in private_endpoints
    assert "category: 'ContainerRegistry'" in acr_connection
    assert "authType: 'ManagedIdentity'" in acr_connection
    assert "clientId: projectPrincipalId" in acr_connection
    assert "resourceId: acrResourceId" in acr_connection
    assert "AZURE_AI_PROJECT_ACR_CONNECTION_NAME" in orchestration


def test_public_profile_hard_codes_public_networking() -> None:
    entrypoint = (INFRA_ROOT / "public" / "main.bicep").read_text(
        encoding="utf-8"
    )

    assert "useVnet: false" in entrypoint
    assert "allowPublicFoundryAccess: true" in entrypoint


def test_profile_parameters_do_not_expose_network_mode_switches() -> None:
    for profile in ("private", "public"):
        parameters = (INFRA_ROOT / profile / "main.parameters.json").read_text(
            encoding="utf-8"
        )

        assert "USE_VNET" not in parameters
        assert "ALLOW_PUBLIC_FOUNDRY_ACCESS" not in parameters


def test_private_manifest_uses_prebuilt_public_acr_images() -> None:
    manifest = (INFRA_ROOT / "private" / "azure.yaml").read_text(encoding="utf-8")

    assert manifest.count("project: .") == 4
    assert manifest.count("language: docker") == 4
    assert manifest.count("imagePassthrough: true") == 4
    assert manifest.count("remoteBuild: false") == 4
    assert manifest.count("${AZURE_CONTAINER_REGISTRY_ENDPOINT=bootstrap.invalid}") == 4
    assert "agents.secret_detection.main" not in manifest
    assert "/secret-detection-agent:${AZURE_ENV_NAME}" in manifest
    assert "workflows:" not in manifest
    assert "run: ./scripts/prepare_public_acr.py" in manifest
    assert "run: ./scripts/build_agent_images.py" in manifest
    assert "codeConfiguration:" not in manifest


def test_public_manifest_uses_prebuilt_public_acr_images() -> None:
    manifest = (INFRA_ROOT / "public" / "azure.yaml").read_text(encoding="utf-8")

    assert manifest.count("project: .") == 4
    assert manifest.count("language: docker") == 4
    assert manifest.count("imagePassthrough: true") == 4
    assert manifest.count("remoteBuild: false") == 4
    assert manifest.count("${AZURE_CONTAINER_REGISTRY_ENDPOINT=bootstrap.invalid}") == 4
    assert "agents.secret_detection.main" not in manifest
    assert "/secret-detection-agent:${AZURE_ENV_NAME}" in manifest
    assert "workflows:" not in manifest
    assert "run: ./scripts/prepare_public_acr.py" in manifest
    assert "run: ./scripts/build_agent_images.py" in manifest
    assert "codeConfiguration:" not in manifest


def test_profile_manifests_use_in_project_hook_launchers() -> None:
    for profile in ("private", "public"):
        manifest = (INFRA_ROOT / profile / "azure.yaml").read_text(encoding="utf-8")

        assert 'azure.ai.projects: ">=1.0.0-beta.14"' in manifest
        assert "postup:" in manifest
        assert "../../scripts" not in manifest
        for hook in (
            "prepare_public_acr",
            "build_agent_images",
            "configure_agent_rbac",
            "deploy_redaction_chat",
            "validate_azd_environment",
        ):
            assert f"run: ./scripts/{hook}.py" in manifest
            assert (INFRA_ROOT / profile / "scripts" / f"{hook}.py").is_file()

        assert "run_hook.py" not in manifest


def test_obsolete_root_deployment_entry_points_are_absent() -> None:
    assert not (REPOSITORY_ROOT / "azure.yaml").exists()
    assert not (INFRA_ROOT / "main.parameters.json").exists()