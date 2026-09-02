# Responsible AI Guardrails

Enterprise-ready Responsible AI guardrails and hosted agents for Microsoft Foundry. The first implementation is a privacy-first **PII Redaction Agent** for text, documents, images, prompts, and model responses.

> This accelerator reduces risk; it does not guarantee that every sensitive value will be detected. Validate against your languages, jurisdictions, document types, and policies before production use.

## Implemented capabilities

- Azure AI Language contextual PII detection with a local structured-data fallback.
- Names, email addresses, phone numbers, physical addresses, driver licence numbers, passport numbers, credit cards, US tax identifiers, IP addresses, and tenant-defined patterns.
- Deterministic overlap handling and irreversible token or mask replacement.
- Azure Document Intelligence extraction for PDF, Office, and image inputs.
- OCR polygon-to-span mapping and opaque pixel redaction for raster images.
- Dedicated endpoints for prompts and AI-generated responses.
- Microsoft Foundry Invocations-protocol hosting without sending PII to a generative model.
- Privacy-safe logs: category names, counts, status, and correlation IDs only.
- Synthetic evaluation data, offline unit tests, CI security checks, and OIDC deployment.

## Repository structure

```text
agents/                         Hosted adapters and agent-specific contracts
  pii_redaction/                Implemented PII Redaction Agent
  */README.md                   Planned specialist agents
shared/guardrails/              Detection, extraction, policy, and redaction library
shared/evaluations/             Deterministic metrics and synthetic datasets
tests/                          Unit and offline evaluation tests
infra/                          Bicep infrastructure templates for private network deployment
docs/                           Architecture, security, RAI, evaluation, deployment
samples/                        Synthetic sample inputs only
.foundry/                       Local Foundry evaluation metadata
.github/workflows/              CI and protected OIDC deployment
```

## Quick start

Prerequisites: Python 3.11 or newer; Python 3.13 is used by the hosted-agent configuration.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
pytest
```

Run the local REST adapter:

```powershell
python -m agents.pii_redaction.run_api
```

Example request:

```powershell
$body = @{ input = 'Contact synthetic.user@example.test'; language = 'en' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/redact/text -ContentType application/json -Body $body
```

For the Microsoft Foundry hosted-agent inner loop, install dependencies and press **F5**. VS Code starts the Invocations host on port 8088 and opens Foundry Toolkit Agent Inspector.

## Azure mode

Use `PII_BACKEND=hybrid` and configure `AZURE_AI_LANGUAGE_ENDPOINT` plus `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`. Authentication uses `DefaultAzureCredential`; do not configure service keys. In Azure, assign the hosted workload identity only the required Cognitive Services data-plane roles.

### Infrastructure Provisioning

The repository includes modular Bicep templates under [`infra/`](./infra/) for deploying with full private network isolation:

- VNet with dedicated agent subnet (delegated to Microsoft.App/environments) and private endpoint subnet
- Microsoft Foundry AIServices, Azure AI Language, Azure Document Intelligence—all with private endpoints and managed identity
- Basic Azure Container Registry with a public endpoint, Microsoft Entra RBAC, and admin access disabled
- Application Insights + Log Analytics + Azure Monitor Private Link Scope
- Private DNS zones for automatic resolution
- Network Security Groups with minimal safe rules

**Default configuration**: East US 2 region, 10.40.0.0/16 VNet, no generative model deployment (deterministic PII agent), Language F0, Document Intelligence F0, Basic ACR, and 0.5-vCPU/1-GiB hosted-agent compute. ACR intentionally uses its public endpoint and Microsoft Entra RBAC; the AI and monitoring services retain private endpoints. Free-tier limits and paid-tier overrides are documented in the deployment guide.

See [`infra/README.md`](./infra/README.md) for architecture details and [`docs/deployment.md`](./docs/deployment.md) for provisioning steps.

**Important**: Deployment requires a VNet-connected execution environment (self-hosted runner, Azure VM, or VPN access) to reach private endpoints. The GitHub deployment workflow is configured for self-hosted runners labeled `vnet-connected`.

## Custom sensitive information

Set `PII_CUSTOM_PATTERNS` to a JSON array:

```json
[
  {
    "name": "EmployeeId",
    "pattern": "EMP-\\d{6}",
    "replacement": "[EMPLOYEE]"
  }
]
```

Only trusted administrators should author expressions. Test them for false positives and denial-of-service behavior before rollout.

## Planned agents

- PII Detection Agent
- Image Redaction Agent
- Content Safety Agent
- Prompt Injection Detection Agent
- Secret & Credential Detection Agent
- DLP Compliance Agent
- Human Review Agent
- Audit & Compliance Agent

See `agents/README.md` for ownership and extension rules.

## Documentation

- Architecture: `docs/architecture.md`
- Responsible AI: `docs/responsible-ai.md`
- Security and threat model: `docs/security.md`
- Evaluation strategy: `docs/evaluation.md`
- Local and Foundry deployment: `docs/deployment.md`

## Secure contribution rules

Never commit or log real PII, credentials, Azure keys, production prompts, or unredacted model responses. Every detector and policy change must include synthetic positive, negative, overlap, and leakage tests. Production releases require per-entity recall review and explicit owner approval.
