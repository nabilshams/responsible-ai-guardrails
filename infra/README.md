# Infrastructure Overview

This directory contains shared Bicep modules and two independent deployment profiles:

- `private/`: VNet injection, private endpoints, private DNS, and private dependent services.
- `public/`: Public service endpoints without VNet resources.

Each folder has its own `azure.yaml`, `main.bicep`, and `main.parameters.json`. Network mode is fixed by the selected folder rather than an environment variable.

## Architecture

The infrastructure provisions:

- **Network in the VNet profile**: VNet (10.40.0.0/16) with dedicated subnets:
  - Agent subnet (10.40.0.0/24) delegated to `Microsoft.App/environments`
  - Private endpoint subnet (10.40.1.0/24)
  - Redaction chat subnet (10.40.2.0/24) delegated to `Microsoft.App/environments`
  - Network Security Groups with minimal safe rules

- **AI Services**:
  - Microsoft Foundry AIServices account S0 (lowest supported Foundry tier, with system identity)
  - Azure AI Language F0 by default (PII detection, managed identity only)
  - Foundry permits authenticated public access while retaining private endpoint and VNet injection in the VNet profile
  - Language and Document Intelligence remain private in the VNet profile

- **Container Infrastructure**:
  - Standard ACR with public network access in both profiles
  - Admin and anonymous registry access disabled; image pulls use managed identities
  - Hosted-agent Docker images built remotely in ACR; Docker Desktop is not required
  - ACR pull access granted to the Foundry project identity
  - Internal Azure Container Apps environment and private redaction chat in the VNet profile

- **Monitoring**:
  - Log Analytics workspace and Application Insights in both modes
  - Azure Monitor Private Link Scope with private ingestion and query access in VNet mode

- **Private DNS Zones in the VNet profile**:
  - `privatelink.cognitiveservices.azure.com` (Azure AI Language)
  - `privatelink.openai.azure.com` (Foundry compatibility)
  - `privatelink.services.ai.azure.com` (Foundry AIServices)
  - `privatelink.monitor.azure.com`, `privatelink.oms.opinsights.azure.com`, `privatelink.ods.opinsights.azure.com`, `privatelink.agentsvc.azure-automation.net` (Azure Monitor)

## Deployment

### Prerequisites

1. **Execution environment**: VNet mode must be provisioned from a VM, Azure DevOps agent, or GitHub self-hosted runner with VNet access; public mode can be provisioned from a normal authenticated workstation
2. **Azure CLI and azd**: Latest versions installed
3. **Permissions**: Contributor access to target subscription/resource group

### Configuration

Each profile's `main.parameters.json` defines its azd environment variable bindings:

- `AZURE_ENV_NAME`: Unique environment identifier (used as resource name prefix)
- `AZURE_LOCATION`: Azure region (default: `eastus2`)
- `VNET_ADDRESS_PREFIX`: VNet CIDR (default: `10.40.0.0/16`)
- `AGENT_SUBNET_PREFIX`: Agent subnet CIDR (default: `10.40.0.0/24`)
- `PE_SUBNET_PREFIX`: Private endpoint subnet CIDR (default: `10.40.1.0/24`)
- `WEB_SUBNET_PREFIX`: Redaction chat subnet CIDR (default: `10.40.2.0/24`)
- `AI_LANGUAGE_SKU`: Language tier (default: `F0`; set to `S` for production volume)

### Cost-Minimized Defaults

The template uses the lowest tiers compatible with each resource role:

- Foundry AIServices remains `S0`, the required standard tier for the Foundry account.
- Both profiles use Standard ACR with public network access. Admin and anonymous access remain disabled.
- Log Analytics remains pay-as-you-go (`PerGB2018`); Application Insights has no separate capacity SKU.
- Azure AI Language defaults to `F0`. Azure permits only a limited number of free-tier resources per subscription, and regional availability can vary. Override the SKU when deployment validation reports that F0 is unavailable.
- Hosted-agent compute is 0.5 vCPU and 1 GiB memory.
- The redaction chat scales from zero to two replicas at 0.5 vCPU and 1 GiB per replica.

The free tier is intended for development and evaluation. Language F0 provides 5,000 free text records per month. Use `AI_LANGUAGE_SKU=S` for production volume.

### Provision With VNet Isolation

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"

azd -C infra/private env new "rai-private" --location "eastus2"

# Optional: override network defaults
azd -C infra/private env set VNET_ADDRESS_PREFIX "10.50.0.0/16"
azd -C infra/private env set AGENT_SUBNET_PREFIX "10.50.0.0/24"
azd -C infra/private env set PE_SUBNET_PREFIX "10.50.1.0/24"
azd -C infra/private env set WEB_SUBNET_PREFIX "10.50.2.0/24"

# Optional: opt into the paid production tier
azd -C infra/private env set AI_LANGUAGE_SKU "S"

# Preview changes
azd -C infra/private provision --preview

# Provision infrastructure and deploy all services
azd -C infra/private up --no-prompt
azd -C infra/private hooks run postup --no-prompt
```

### Provision Without A VNet

Public mode skips the VNet, delegated subnet, private endpoint subnet, private endpoints, private DNS zones, and Azure Monitor Private Link Scope. It enables authenticated public endpoints for Foundry and the supporting data-plane services. The template also creates the account-level and project-level capability hosts required by hosted agents.

Use a new azd environment and Foundry account. Do not reuse an environment from the VNet folder because Hosted Agent network injection is fixed when the Foundry account is created.

Run the following commands from the repository root. Replace the example environment name, tenant ID, and subscription ID with your values:

```powershell
# Keep Foundry attribution scoped to this terminal session.
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"

# Authenticate azd directly to the tenant that owns the target subscription.
azd auth logout
azd auth login --tenant-id "<tenant-id>" --use-device-code
azd auth login --check-status

# Create and select a fresh environment.
azd -C infra/public env new "rai-public" `
  --location "eastus2" `
  --subscription "<subscription-id>" `
  --no-prompt

# Use paid tiers when the subscription already contains its allowed free-tier resources.
azd -C infra/public env set AI_LANGUAGE_SKU "S"
azd -C infra/public env set DOCUMENT_INTELLIGENCE_SKU "S0"

# Agent defaults.
azd -C infra/public env set PII_CONFIDENCE_THRESHOLD "0.7"
azd -C infra/public env set PII_DEFAULT_LANGUAGE "en"

# Review the selected environment and validate the Azure deployment.
azd -C infra/public env get-values
azd -C infra/public provision --preview

# Provision infrastructure and deploy all hosted agents.
azd -C infra/public up --no-prompt
azd -C infra/public hooks run postup --no-prompt
```

`azd up` now populates the selected azd environment in both phases:

- `azd provision` writes Azure context, selected deployment settings, resource IDs, and service endpoints from Bicep outputs.
- `azd deploy` writes each hosted agent's name, version, runtime identity, and invocation endpoint.
- The `postup` hooks configure managed-identity RBAC, remotely build and deploy the redaction chat, inject agent endpoints into its server-side environment, and validate required variable names without printing their values.
- Bicep provisions Azure AI Speech separately from Azure AI Language and exports `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_RESOURCE_ID`; the demo uses Speech for narration.

Defaults such as network prefixes, SKUs, `PII_CONFIDENCE_THRESHOLD`, and `PII_DEFAULT_LANGUAGE` are also emitted as outputs, so they appear in `azd env get-values` even when the user did not set them explicitly. Public deployments retain empty VNet resource IDs by design.

To provision infrastructure without deploying the agents, replace the final command with:

```powershell
azd -C infra/public provision --no-prompt
```

If infrastructure succeeds but an agent deployment fails, retry only the deployment:

```powershell
azd -C infra/public deploy --no-prompt
```

The `S` and `S0` Cognitive Services tiers incur usage charges. The Speech resource uses `S0`. You can try `F0` only when the subscription has free-tier capacity available.

In VNet mode, Storage public network access remains disabled. Native PDF, DOCX, and TXT redaction must use a private service-to-storage path; do not enable Storage public access as a workaround.

## Post-Deployment: Agent Identity RBAC

The Bicep templates configure ACR pull access for the Foundry project identity and Storage access for the Azure AI Language identity. Each hosted agent's runtime identity is created only during `azd deploy`, after infrastructure provisioning, so `azd up` runs `scripts/configure_agent_rbac.py` as a `postup` hook. The hook checks and creates these resource-scoped assignments without displaying identity or resource IDs:

| Hosted agent | Resource scope | Built-in role |
| --- | --- | --- |
| PII Redaction Agent | Azure AI Language | Cognitive Services User |
| Secret Detection Agent | None | No additional resource role required |
| Document Redaction Agent | Azure AI Language | Cognitive Services User |
| Document Redaction Agent | Temporary document Storage account | Storage Blob Data Contributor |
| Image Redaction Agent | Azure AI Language | Cognitive Services User |
| Image Redaction Agent | Document Intelligence | Cognitive Services User |
| Redaction Chat | Foundry project | Foundry User |

Use resource-level scopes rather than the resource group or subscription. `Cognitive Services Language Reader` does not include the native `/language/analyze-documents/jobs` operation and is not sufficient for PDF, DOCX, or TXT redaction.

The hooks are idempotent. Azure CLI must be installed and authenticated with permission to read and create role assignments, run ACR builds, and update the Container App. Run them after `azd up` or `azd deploy` so new agent versions receive RBAC and the redaction chat is refreshed with their current endpoints:

```powershell
azd hooks run postup --no-prompt
```

### Manual recovery

If the automatic hook cannot create role assignments, grant the Document Redaction Agent its two required roles manually:

```powershell
# Resolve the deployed runtime identity and Bicep resource outputs.
$agent = azd ai agent show document-redaction-agent --output json |
    ConvertFrom-Json
$agentIdentityId = [string]$agent.instance_identity.principal_id
$environment = azd env get-values --output json |
    ConvertFrom-Json -AsHashtable

az role assignment create `
  --assignee-object-id $agentIdentityId `
  --assignee-principal-type ServicePrincipal `
  --role "Cognitive Services User" `
  --scope $environment["AZURE_AI_LANGUAGE_RESOURCE_ID"] `
  --output none

az role assignment create `
  --assignee-object-id $agentIdentityId `
  --assignee-principal-type ServicePrincipal `
  --role "Storage Blob Data Contributor" `
  --scope $environment["AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID"] `
  --output none
```

Role assignments can take several minutes to propagate. An invocation made immediately afterward can return `HTTP 422` with an inner `HTTP 401 (PermissionDenied)`; retry after propagation completes.

## Validation

### Check Private Endpoints

For VNet mode:

```powershell
# List private endpoints and their connection states
az network private-endpoint list --resource-group rg-rai-dev --output table
```

All endpoints should show `Approved` connection state.

For public mode, the same command should return no private endpoints.

### Verify DNS Resolution

From a VM inside the VNet:

```powershell
# Should resolve to private IP (10.40.1.x range)
Resolve-DnsName your-aiservices-name.cognitiveservices.azure.com
Resolve-DnsName your-language-name.cognitiveservices.azure.com
```

### Test Agent Access

Use Agent Inspector or direct invocation to verify the agent can access Azure AI Language:

```powershell
# Example invocation (replace with actual endpoint)
Invoke-RestMethod -Method Post -Uri "https://your-agent-endpoint/invoke" `
  -ContentType "application/json" `
  -Body '{"input":"Contact test@example.com","language":"en"}'
```

## Module Reference

| Module | Purpose | Key Resources |
| ------ | ------- | ------------- |
| `private/` | Fixed private VNet deployment | azd manifest, parameters, and Bicep entry point |
| `public/` | Fixed public deployment | azd manifest, parameters, and Bicep entry point |
| `main.bicep` | Shared orchestration | Coordinates all modules for both profiles |
| `modules/network.bicep` | Network infrastructure | VNet, subnets, NSGs |
| `modules/dns.bicep` | Private DNS | Service private DNS zones + VNet links |
| `modules/monitoring.bicep` | Observability | Log Analytics, App Insights, AMPLS |
| `modules/acr.bicep` | Container registry | Standard public ACR with admin access disabled |
| `modules/ai.bicep` | AI services | AIServices and Azure AI Language |
| `modules/foundryProject.bicep` | Foundry workspace | Project capability host and public-mode account capability host |
| `modules/foundryMonitoringConnection.bicep` | Foundry observability | Shared Application Insights connection |
| `modules/privateEndpoints.bicep` | Private connectivity | Service private endpoints with DNS groups |
| `modules/rbac.bicep` | Access control | ACR pull role for AI Services |
| `modules/redactionChat.bicep` | Web redaction host | Container Apps environment, app identity, ingress, and ACR pull |

## Security Notes

- **No secrets in source control**: All authentication uses managed identities or DefaultAzureCredential
- **Explicit network posture**: The VNet folder permits authenticated public access to Foundry and ACR while keeping the redaction chat, Language, Document Intelligence, Storage, and monitoring private
- **Layered access**: Private network reachability is required in addition to Microsoft Entra authentication and RBAC
- **Least privilege**: The Foundry project and web identities have ACR pull only where needed; hosted runtime identities receive the listed resource-scoped roles; the web identity receives Foundry User only at the project scope
- **Audit logs**: All resources send diagnostics to Log Analytics
- **Network isolation**: NSGs enforce minimal safe rules; egress to Azure services via service tags

## Limitations

- **Deployment network access**: VNet deployments and invocation require a VNet-connected environment; use the public profile for workstation-based access
- **Immutable Foundry injection**: Switching between the public and VNet folders requires a new environment and Foundry account
- **No generative model**: This template provisions deterministic PII detection only; add model deployments separately if needed
- **Agent identity RBAC timing**: Agent runtime identity doesn't exist until first deploy; manual role assignment may be required
- **Azure Firewall not included**: Egress uses service tags; add Azure Firewall for FQDN-level control if required

## API Versions

- Foundry account/project: `2025-04-01-preview`
- Azure AI Language: `2024-10-01`
- Container Registry: `2023-07-01`
- Container Apps: `2024-03-01`
- Network resources: `2024-05-01` / `2024-06-01`
- OperationalInsights/workspaces: `2023-09-01`
- Insights components: `2020-02-02`

API versions validated via `bicepschema_get` and official Azure resource schemas.
