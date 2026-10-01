# Deployment

## Local Development

1. Create `.venv` and install `requirements-dev.txt`.
2. Copy `.env.example` to `.env`.
3. Configure `AZURE_AI_LANGUAGE_ENDPOINT` for all agents and `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` for document/image agents; authentication uses `DefaultAzureCredential`.
4. Hosted agents are Docker containers built remotely in Azure Container Registry. The web chat image also uses an Azure Container Registry Task. Neither path requires a local Docker daemon.
5. Select the desired specialist debug profile and press F5 to start its Invocations protocol host on port 8088 and open Agent Inspector.
6. Run `python -m agents.pii_redaction.run_api` for the optional REST adapter on port 8000.

## Azure Infrastructure Provisioning

This solution provides two independent azd projects: `infra/private` for VNet-backed private networking and `infra/public` for public networking. Their network modes are fixed in Bicep and cannot be changed through environment variables.

### Prerequisites

- **Execution environment**: VNet deployments require a VNet-connected VM, self-hosted runner, VPN, or ExpressRoute path; public deployments can run from an authenticated workstation
- **Azure CLI**: Version 2.50.0 or newer
- **Azure Developer CLI (azd)**: Version 1.27.1 or newer
- **Permissions**: Contributor plus Role Based Access Administrator, or Owner, so the deployment can create scoped RBAC assignments

### Architecture

The Bicep templates provision:

- **Private network in VNet mode**: VNet (default 10.40.0.0/16) with agent, private endpoint, and redaction chat subnets
- **AI Services**: Foundry retains its private endpoint and VNet injection but permits authenticated public access in VNet mode; Azure AI Language and Document Intelligence disable public access
- **Container Registry**: Standard ACR with public network access in both profiles; admin access is disabled and image pulls use managed identities
- **Redaction chat**: Internal Container Apps environment with private DNS in VNet mode; public ingress in public mode
- **Monitoring**: Application Insights and Log Analytics in both modes; ingestion and query access use Azure Monitor Private Link Scope in VNet mode
- **Private DNS in VNet mode**: Private DNS zones linked to the VNet for automatic private endpoint resolution
- **RBAC**: Foundry project identity receives ACR pull access; each agent runtime identity receives only its required Cognitive Services User and Storage Blob Data Contributor assignments

See [`infra/README.md`](../infra/README.md) for detailed architecture and module reference.

### Default Configuration

Default values (customizable via azd environment variables):

- **Region**: East US 2
- **Network mode**: The VNet profile permits authenticated public access to Foundry and ACR while disabling public access for the redaction chat and dependent services
- **VNet CIDR**: 10.40.0.0/16
- **Agent subnet**: 10.40.0.0/24
- **Private endpoint subnet**: 10.40.1.0/24
- **Redaction chat subnet**: 10.40.2.0/24
- **No generative model deployment**: This template provisions deterministic PII detection only
- **Container Registry**: Standard public ACR in both profiles, with admin and anonymous access disabled
- **Hosted-agent compute**: 0.5 vCPU and 1 GiB memory per specialist

Both profiles use ordinary remote ACR builds against a Standard registry with public network access. The private profile's custom `azd up` workflow provisions before packaging so the generated registry endpoint is available when passthrough image references are resolved. Registry access is authenticated through Azure RBAC; no admin credentials or anonymous pulls are enabled. Docker Desktop is not required for either profile.

### VNet Deployment

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd -C infra/private env new "rai-private" --location "eastus2"

# 3. Optional: override network defaults
azd -C infra/private env set VNET_ADDRESS_PREFIX "10.50.0.0/16"
azd -C infra/private env set AGENT_SUBNET_PREFIX "10.50.0.0/24"
azd -C infra/private env set PE_SUBNET_PREFIX "10.50.1.0/24"
azd -C infra/private env set WEB_SUBNET_PREFIX "10.50.2.0/24"

# Optional: use paid tiers for production volume
azd -C infra/private env set AI_LANGUAGE_SKU "S"
azd -C infra/private env set DOCUMENT_INTELLIGENCE_SKU "S0"

# 4. Preview infrastructure changes (recommended)
azd -C infra/private provision --preview

# 5. Provision and deploy in one step
azd -C infra/private up --no-prompt
```

Run these commands from a VNet-connected execution environment because the deployment hooks and supporting services require private network reachability. The Foundry endpoint permits authenticated public access, but Microsoft Entra authentication and project RBAC remain required and local authentication is disabled. The redaction chat, ACR, Azure AI Language, Document Intelligence, Storage, and monitoring have no public data-plane access in this profile.

### Public Deployment

Create a separate environment under the public profile:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd -C infra/public env new "rai-public" --location "eastus2"
azd -C infra/public up --no-prompt
```

Do not reuse an environment across the two folders. Hosted Agent network injection cannot be added or changed after account creation.

### Post-Deployment: Agent Identity RBAC

Each runtime managed identity is created only during `azd deploy`. The `azd up` `postup` hook runs `scripts/configure_agent_rbac.py` to check and create these resource-scoped assignments:

| Hosted agent | Required role assignments |
| --- | --- |
| PII Redaction Agent | `Cognitive Services User` on Azure AI Language |
| Secret Detection Agent | No additional Azure resource role |
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
4. Select the `private` or `public` workflow profile
5. Preview and deploy through that profile's `infra/<profile>` azd project

No secrets are stored in the repository; all authentication uses OIDC federation.

### Azure DevOps

For Azure DevOps pipelines in VNet mode:

1. Use a self-hosted agent in the VNet or with private endpoint access
2. Configure a service connection with managed identity or federated credential
3. Run `azd -C infra/private provision` and `azd -C infra/private deploy` in sequence
4. Validate private endpoint connectivity before deployment

## Invocation Payloads

Text:

```json
{"input":"Contact synthetic.user@example.test","language":"en"}
```

The response streams a JSON object containing redacted text and entity metadata without original values.
