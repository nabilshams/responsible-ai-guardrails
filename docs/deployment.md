# Deployment

## Local Development

1. Create `.venv` and install `requirements-dev.txt`.
2. Copy `.env.example` to `.env`.
3. Configure `AZURE_AI_LANGUAGE_ENDPOINT` for all agents and `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` for document/image agents; authentication uses `DefaultAzureCredential`.
4. Hosted-agent images are built remotely by Azure Container Registry Tasks. A local Docker daemon is not required.
5. Select the desired specialist debug profile and press F5 to start its Invocations protocol host on port 8088 and open Agent Inspector.
6. Run `python -m agents.pii_redaction.run_api` for the optional REST adapter on port 8000.

## Azure Infrastructure Provisioning

This solution uses custom Bicep templates with a `USE_VNET` switch for either public networking or VNet isolation.

### Prerequisites

- **Execution environment**: VNet mode requires a VM, Azure Bastion, Azure DevOps agent, or GitHub self-hosted runner with target VNet connectivity; public mode can deploy from a normal authenticated workstation
- **Azure CLI**: Version 2.50.0 or newer
- **Azure Developer CLI (azd)**: Version 1.27.1 or newer
- **Permissions**: Contributor plus Role Based Access Administrator, or Owner, so the deployment can create scoped RBAC assignments

### Architecture

The Bicep templates provision:

- **Private network in VNet mode**: VNet (default 10.40.0.0/16) with agent subnet (10.40.0.0/24, delegated to Microsoft.App/environments) and private endpoint subnet (10.40.1.0/24)
- **AI Services**: Microsoft Foundry AIServices, Azure AI Language, and Document Intelligence use private endpoints in VNet mode and authenticated public endpoints in public mode
- **Container Registry**: Basic Azure Container Registry with public network access, admin user disabled, and Microsoft Entra RBAC
- **Monitoring**: Application Insights and Log Analytics in both modes; Azure Monitor Private Link Scope in VNet mode
- **Private DNS in VNet mode**: Private DNS zones linked to the VNet for automatic private endpoint resolution
- **RBAC**: Foundry project identity receives ACR pull access; each agent runtime identity receives only its required Cognitive Services User and Storage Blob Data Contributor assignments

See [`infra/README.md`](../infra/README.md) for detailed architecture and module reference.

### Default Configuration

Default values (customizable via azd environment variables):

- **Region**: East US 2
- **Network mode**: VNet isolation by default; set `USE_VNET=false` for public networking
- **VNet CIDR**: 10.40.0.0/16
- **Agent subnet**: 10.40.0.0/24
- **Private endpoint subnet**: 10.40.1.0/24
- **No generative model deployment**: This template provisions deterministic PII detection only
- **Cost-minimized SKUs**: Language F0, Document Intelligence F0, Foundry AIServices S0, Basic ACR, and pay-as-you-go Log Analytics
- **Hosted-agent compute**: 0.5 vCPU and 1 GiB memory per specialist

ACR uses the lowest `Basic` tier and intentionally does not use Private Link. Its public endpoint is required for image push/pull, while Microsoft Entra RBAC and a disabled admin account protect access. Foundry AIServices remains S0. Language and Document Intelligence use F0 development defaults. Free-tier resource count and regional availability restrictions apply. For production volume, set `AI_LANGUAGE_SKU=S` and `DOCUMENT_INTELLIGENCE_SKU=S0` before provisioning.

### Deployment Steps

```powershell
# 1. Initialize azd environment
azd init

# 2. Configure environment
azd env set AZURE_ENV_NAME "rai-prod"
azd env set AZURE_LOCATION "eastus2"
azd env set USE_VNET "true"

# 3. Optional: override network defaults
azd env set VNET_ADDRESS_PREFIX "10.50.0.0/16"
azd env set AGENT_SUBNET_PREFIX "10.50.0.0/24"
azd env set PE_SUBNET_PREFIX "10.50.1.0/24"

# Optional: use paid tiers for production volume
azd env set AI_LANGUAGE_SKU "S"
azd env set DOCUMENT_INTELLIGENCE_SKU "S0"

# 4. Preview infrastructure changes (recommended)
azd provision --preview

# 5. Provision and deploy in one step
azd up --no-prompt
```

For public networking, create a separate environment and use:

```powershell
azd env new rai-public
azd env set AZURE_LOCATION "eastus2"
azd env set USE_VNET "false"
azd up --no-prompt
```

Do not change `USE_VNET` for an existing Foundry account. Hosted Agent network injection cannot be added or changed after account creation; use a new azd environment when switching modes.

### Post-Deployment: Agent Identity RBAC

Each runtime managed identity is created only during `azd deploy`. The `azd up` `postup` hook runs `scripts/configure_agent_rbac.py` to check and create these resource-scoped assignments:

| Hosted agent | Required role assignments |
| --- | --- |
| PII Redaction Agent | `Cognitive Services User` on Azure AI Language |
| Document Redaction Agent | `Cognitive Services User` on Azure AI Language; `Storage Blob Data Contributor` on temporary document Storage |
| Image Redaction Agent | `Cognitive Services User` on Azure AI Language and Document Intelligence |

`Cognitive Services Language Reader` does not authorize native document jobs; use `Cognitive Services User` as shown below.

The hook is idempotent and does not display identity or resource IDs. Azure CLI must be installed and authenticated with permission to read and create role assignments. Run the hook again after a standalone `azd deploy`, which can create a new runtime identity:

```powershell
az login
azd env get-values | ForEach-Object {
   if ($_ -match '^([^=]+)="(.*)"$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
   }
}
.\.venv\Scripts\python.exe scripts\configure_agent_rbac.py
```

If the automatic hook fails, recover the Document Redaction Agent assignments manually:

```powershell
$agent = azd ai agent show document-redaction-agent --output json | ConvertFrom-Json
$environment = azd env get-values --output json | ConvertFrom-Json -AsHashtable

az role assignment create `
   --assignee-object-id $agent.instance_identity.principal_id `
   --assignee-principal-type ServicePrincipal `
   --role "Cognitive Services User" `
   --scope $environment["AZURE_AI_LANGUAGE_RESOURCE_ID"]

az role assignment create `
   --assignee-object-id $agent.instance_identity.principal_id `
   --assignee-principal-type ServicePrincipal `
   --role "Storage Blob Data Contributor" `
   --scope $environment["AZURE_DOCUMENT_PII_STORAGE_RESOURCE_ID"]
```

Allow several minutes for RBAC propagation before testing.

### Validation

For VNet mode:

1. **Private endpoints**: Verify all endpoints show `Approved` state:

   ```powershell
   az network private-endpoint list --resource-group rg-<env-name> --output table
   ```

2. **DNS resolution**: From a VNet-connected VM, confirm private DNS resolves to private IPs:

   ```powershell
   Resolve-DnsName <aiservices-name>.cognitiveservices.azure.com
   ```

3. **Agent functionality**: Test an invocation via Agent Inspector or direct API call

For public mode, confirm the private endpoint list is empty and invoke the agent from an authenticated workstation.

## CI/CD

### GitHub Actions

The deployment workflow uses OIDC authentication. VNet mode requires a **self-hosted runner with VNet connectivity**; public mode can use a Microsoft-hosted runner.

**Required GitHub environment variables**:

- `AZURE_CLIENT_ID`: Federated identity credential client ID
- `AZURE_TENANT_ID`: Microsoft Entra ID tenant ID
- `AZURE_SUBSCRIPTION_ID`: Target subscription ID
- `AZURE_LOCATION`: Deployment region (e.g., `eastus2`)

**Self-hosted runner setup**:

1. Deploy a VM inside the VNet (or with VPN/ExpressRoute access)
2. Install GitHub Actions runner
3. Label the runner with `self-hosted` and `vnet-connected`
4. Update `.github/workflows/deploy.yml` `runs-on` to use these labels

**Workflow steps**:

1. Checkout code
2. Authenticate with Azure using OIDC
3. Authenticate azd with federated credential
4. Run `azd provision --preview` to preview changes
5. Run `azd up --no-prompt` to provision and deploy

No secrets are stored in the repository; all authentication uses OIDC federation.

### Azure DevOps

For Azure DevOps pipelines in VNet mode:

1. Use a self-hosted agent in the VNet or with private endpoint access
2. Configure a service connection with managed identity or federated credential
3. Run `azd provision` and `azd deploy` tasks in sequence
4. Validate private endpoint connectivity before deployment

## Invocation Payloads

Text:

```json
{"input":"Contact synthetic.user@example.test","language":"en"}
```

The response streams a JSON object containing redacted text and entity metadata without original values.
