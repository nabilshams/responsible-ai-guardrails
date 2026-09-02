# Responsible AI Guardrails

Enterprise-ready Responsible AI guardrails and hosted agents for Microsoft Foundry. The implementation separates text, document, and image redaction into independently deployable specialists.

> This accelerator reduces risk; it does not guarantee that every sensitive value will be detected. Validate against your languages, jurisdictions, and policies before production use.

## Implemented capabilities

- Azure AI Language contextual PII detection as the only detection backend.
- Text categories supported by Azure AI Language, including names, contact details, addresses, and identity information.
- Deterministic overlap handling and irreversible token or mask replacement.
- PII Redaction Agent for text, prompts, and AI-generated responses.
- Document Redaction Agent using Azure AI Language document-based PII for layout-preserving `.txt`, `.pdf`, and `.docx` output. Structured UTF-8 `.csv`, `.json`, `.xml`, `.md`, and `.log` inputs use the existing redacted-text path.
- Image Redaction Agent using Document Intelligence OCR geometry and Azure AI Language PII detection to burn masks into a redacted PNG.
- Microsoft Foundry Invocations-protocol hosting without sending PII to a generative model.
- Privacy-safe logs: category names, counts, status, and correlation IDs only.
- Synthetic evaluation data, offline unit tests, CI security checks, and OIDC deployment.

## Repository structure

```text
agents/                         Hosted adapters and agent-specific contracts
  pii_redaction/                Implemented PII Redaction Agent
  document_redaction/           Implemented Document Redaction Agent
  image_redaction/              Implemented Image Redaction Agent
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

### Live document test executor

The sequential live executor reads visibly synthetic `.txt`, `.csv`, `.json`, `.xml`, `.md`, and `.log` files from `samples/input`, invokes the deployed Document Redaction Agent once per file, and writes redacted text to `samples/output` using the same filename.

Authenticate with an Azure identity that can invoke the hosted agent and set `AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT` to its full Invocations endpoint. Then run:

```powershell
python -m scripts.live_document_executor
```

Use `--file synthetic.txt` to process one selected file and `--overwrite` to replace an existing output. Input and output contents and filenames are not logged. See [`samples/README.md`](./samples/README.md) for details.

## Azure mode

Configure `AZURE_AI_LANGUAGE_ENDPOINT` for every agent and `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` for document and image agents. Authentication uses `DefaultAzureCredential`; do not configure service keys. Assign each hosted workload identity only the Cognitive Services User data-plane roles required by that specialist.

### Infrastructure Provisioning

The repository includes modular Bicep templates under [`infra/`](./infra/) for deploying with full private network isolation:

- VNet with dedicated agent subnet (delegated to Microsoft.App/environments) and private endpoint subnet
- Microsoft Foundry AIServices and Azure AI Language with private endpoints and managed identity
- Basic Azure Container Registry with a public endpoint, Microsoft Entra RBAC, and admin access disabled
- Application Insights + Log Analytics + Azure Monitor Private Link Scope
- Private DNS zones for automatic resolution
- Network Security Groups with minimal safe rules

**Default configuration**: East US 2 region, 10.40.0.0/16 VNet, no generative model deployment, Language F0, Basic ACR, and 0.5-vCPU/1-GiB hosted-agent compute. ACR intentionally uses its public endpoint and Microsoft Entra RBAC; Azure AI Language and monitoring retain private endpoints. Free-tier limits and paid-tier overrides are documented in the deployment guide.

See [`infra/README.md`](./infra/README.md) for architecture details and [`docs/deployment.md`](./docs/deployment.md) for provisioning steps.

**Important**: Deployment requires a VNet-connected execution environment (self-hosted runner, Azure VM, or VPN access) to reach private endpoints. The GitHub deployment workflow is configured for self-hosted runners labeled `vnet-connected`.

## Additional planned agents

- PII Detection Agent
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
