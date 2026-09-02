# Infrastructure Overview

This directory contains modular Bicep templates for provisioning the Responsible AI Guardrails Microsoft Foundry hosted-agent solution with private network infrastructure.

## Architecture

The infrastructure provisions:

- **Network**: VNet (10.40.0.0/16) with dedicated subnets:
  - Agent subnet (10.40.0.0/24) delegated to `Microsoft.App/environments`
  - Private endpoint subnet (10.40.1.0/24)
  - Network Security Groups with minimal safe rules

- **AI Services**:
  - Microsoft Foundry AIServices account S0 (lowest supported Foundry tier, with system identity)
  - Azure AI Language F0 by default (PII detection, managed identity only)
  - Foundry public access is configurable and enabled by the azd parameter binding; Azure AI Language remains private-only

- **Container Infrastructure**:
  - Azure Container Registry Basic with public network access, Microsoft Entra RBAC, and no admin/anonymous access
  - ACR pull access granted to the Foundry project identity

- **Monitoring**:
  - Log Analytics workspace (private ingestion/query)
  - Application Insights (private ingestion/query)
  - Azure Monitor Private Link Scope with all required DNS zones

- **Private DNS Zones**:
  - `privatelink.cognitiveservices.azure.com` (Azure AI Language)
  - `privatelink.openai.azure.com` (Foundry compatibility)
  - `privatelink.services.ai.azure.com` (Foundry AIServices)
  - `privatelink.monitor.azure.com`, `privatelink.oms.opinsights.azure.com`, `privatelink.ods.opinsights.azure.com`, `privatelink.agentsvc.azure-automation.net` (Azure Monitor)

## Deployment

### Prerequisites

1. **VNet-connected execution environment**: Provision from a VM, Azure DevOps agent, or GitHub self-hosted runner with access to the VNet
2. **Azure CLI and azd**: Latest versions installed
3. **Permissions**: Contributor access to target subscription/resource group

### Default Configuration

The `main.parameters.json` file defines azd environment variable bindings:

- `AZURE_ENV_NAME`: Unique environment identifier (used as resource name prefix)
- `AZURE_LOCATION`: Azure region (default: `eastus2`)
- `FOUNDRY_PUBLIC_NETWORK_ACCESS`: Foundry public endpoint state (default: `Enabled`; set to `Disabled` for VNet-only deployment)
- `VNET_ADDRESS_PREFIX`: VNet CIDR (default: `10.40.0.0/16`)
- `AGENT_SUBNET_PREFIX`: Agent subnet CIDR (default: `10.40.0.0/24`)
- `PE_SUBNET_PREFIX`: Private endpoint subnet CIDR (default: `10.40.1.0/24`)
- `AI_LANGUAGE_SKU`: Language tier (default: `F0`; set to `S` for production volume)

### Cost-Minimized Defaults

The template uses the lowest tiers compatible with each resource role:

- Foundry AIServices remains `S0`, the required standard tier for the Foundry account.
- ACR uses `Basic`, the lowest tier. It intentionally has no private endpoint; its public endpoint is protected by Microsoft Entra RBAC and the admin account is disabled.
- Log Analytics remains pay-as-you-go (`PerGB2018`); Application Insights has no separate capacity SKU.
- Azure AI Language defaults to `F0`. Azure permits only a limited number of free-tier resources per subscription, and regional availability can vary. Override the SKU when deployment validation reports that F0 is unavailable.
- Hosted-agent compute is 0.5 vCPU and 1 GiB memory.

The free tier is intended for development and evaluation. Language F0 provides 5,000 free text records per month. Use `AI_LANGUAGE_SKU=S` for production volume.

### Provision with azd

```powershell
# Initialize environment
azd init

# Set core parameters
azd env set AZURE_ENV_NAME "rai-dev"
azd env set AZURE_LOCATION "eastus2"
azd env set FOUNDRY_PUBLIC_NETWORK_ACCESS "Enabled"

# Optional: override network defaults
azd env set VNET_ADDRESS_PREFIX "10.50.0.0/16"
azd env set AGENT_SUBNET_PREFIX "10.50.0.0/24"
azd env set PE_SUBNET_PREFIX "10.50.1.0/24"

# Optional: opt into the paid production tier
azd env set AI_LANGUAGE_SKU "S"

# Preview changes
azd provision --preview

# Provision infrastructure (creates resource group and all resources)
azd provision

# Deploy the agent (builds image, pushes to ACR, deploys to Foundry)
azd deploy
```

Or provision and deploy in one command:

```powershell
azd up --no-prompt
```

## Post-Deployment: Agent Identity RBAC

The Bicep templates configure ACR pull access for the Foundry project identity. However, **the hosted agent's runtime identity is created only during `azd deploy`**, after infrastructure provisioning.

Once deployed, grant the agent identity data-plane access to Azure AI Language:

```powershell
# Get the agent identity principal ID (from Foundry agent resource)
$agentIdentityId = az ... # (azd may output this, or query the agent resource)

# Cognitive Services User role (data-plane read access)
$cognitiveServicesUserRole = "a97b65f3-24c7-4388-baec-2e87135dc908"

# Resource IDs are emitted by Bicep into the azd environment.
$environment = azd env get-values --output json | ConvertFrom-Json

# Grant access to AI Language
az role assignment create `
  --assignee $agentIdentityId `
  --role $cognitiveServicesUserRole `
  --scope $environment.AZURE_AI_LANGUAGE_RESOURCE_ID

```

> **Note**: If azd's hosted-agent deployment supports automatic RBAC assignment for agent identity, this step may be handled automatically. Verify by testing agent invocations.

## Validation

### Check Private Endpoints

```powershell
# List private endpoints and their connection states
az network private-endpoint list --resource-group rg-rai-dev --output table
```

All endpoints should show `Approved` connection state.

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
| `main.bicep` | Orchestration | Coordinates all modules |
| `modules/network.bicep` | Network infrastructure | VNet, subnets, NSGs |
| `modules/dns.bicep` | Private DNS | 7 private DNS zones + VNet links |
| `modules/monitoring.bicep` | Observability | Log Analytics, App Insights, AMPLS |
| `modules/acr.bicep` | Container registry | Basic public ACR with diagnostics and RBAC-only access |
| `modules/ai.bicep` | AI services | AIServices and Azure AI Language |
| `modules/foundryProject.bicep` | Foundry workspace | Project and Basic capability host |
| `modules/foundryMonitoringConnection.bicep` | Foundry observability | Shared Application Insights connection |
| `modules/privateEndpoints.bicep` | Private connectivity | 3 private endpoints with DNS groups |
| `modules/rbac.bicep` | Access control | ACR pull role for AI Services |

## Security Notes

- **No secrets in source control**: All authentication uses managed identities or DefaultAzureCredential
- **Scoped public access**: Foundry public access is configurable to support workstation deployment; Azure AI Language and monitoring remain private-only. ACR intentionally uses a public endpoint with Microsoft Entra RBAC and its admin account disabled
- **Least privilege**: AI Services has only ACR pull; agent identity requires explicit Cognitive Services User assignment
- **Audit logs**: All resources send diagnostics to Log Analytics
- **Network isolation**: NSGs enforce minimal safe rules; egress to Azure services via service tags

## Limitations

- **Deployment network access**: Workstation deployment requires Foundry public access; private-only deployments must run from a VNet-connected environment
- **No generative model**: This template provisions deterministic PII detection only; add model deployments separately if needed
- **Agent identity RBAC timing**: Agent runtime identity doesn't exist until first deploy; manual role assignment may be required
- **Azure Firewall not included**: Egress uses service tags; add Azure Firewall for FQDN-level control if required

## API Versions

- Foundry account/project: `2025-04-01-preview`
- Azure AI Language: `2024-10-01`
- Container Registry: `2023-07-01`
- Network resources: `2024-05-01` / `2024-06-01`
- OperationalInsights/workspaces: `2023-09-01`
- Insights components: `2020-02-02`

API versions validated via `bicepschema_get` and official Azure resource schemas.
