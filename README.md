# Responsible AI Guardrails

Azure AI Language-based PII redaction for text and native documents, exposed through independently deployable Microsoft Foundry hosted agents.

This repository is an accelerator, not a guarantee that every sensitive value will be detected. Validate detection categories, supported languages, accuracy, and retention against the policies that apply to your organization before processing production data.

## What Can Be Redacted

| Input | Redaction path | Output |
| --- | --- | --- |
| Text, prompts, and responses | Azure AI Language text PII | Redacted text plus category counts |
| `.txt`, `.pdf`, `.docx` | Azure AI Language Document-based PII | Redacted native document |
| `.csv`, `.json`, `.xml`, `.md`, `.log` | Azure AI Language text PII | Redacted UTF-8 text |
| Images | Document Intelligence OCR geometry and Azure AI Language PII | Redacted PNG |

Native document redaction uploads each PDF, DOCX, or TXT file to private temporary Blob Storage, submits an asynchronous Azure AI Language job, retrieves the redacted native artifact, and attempts to delete temporary artifacts. A storage lifecycle rule provides fallback cleanup.

## Architecture At A Glance

```text
agents/                         Hosted agent adapters
  pii_redaction/                Text PII Redaction Agent
  document_redaction/           Native and structured document redaction
  image_redaction/              Image PII redaction
shared/guardrails/              Detection, policies, document services, and native PII adapter
scripts/                        Live invocation, executor, and synthetic-fixture utilities
samples/                        Synthetic inputs and ignored local outputs
tests/                          Offline and opt-in live tests
infra/                          Bicep infrastructure templates
docs/                           Architecture, security, evaluation, and deployment guidance
```

## Security Model

- Azure AI Language is the PII detection and redaction service. This solution does not send document content to a generative model.
- Authentication uses `DefaultAzureCredential`; do not add Azure service keys, connection strings, SAS tokens, or production PII to source control.
- Keep source files and generated outputs outside Git. Supplied sample files are visibly synthetic only.
- The deployed Document Redaction Agent returns native document bytes as base64 over the Invocations protocol. The executor decodes them and writes the result to disk.
- Privacy-safe application logs must not contain original or redacted document content.

## Choose A Workflow

| Goal | Start here |
| --- | --- |
| Develop or test text redaction locally | [Local Development](#local-development) |
| Redact documents with an existing deployment | [Use The Deployed Document Agent](#use-the-deployed-document-agent) |
| Provision a new public deployment | [Deploy Without A VNet](#deploy-without-a-vnet) |

## Local Development

Python 3.11 or newer is required. The hosted-agent configuration uses Python 3.13.

Set up the local environment from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Run offline tests before changing redaction behavior:

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov -q
```

### Local Text API

Run the PII Redaction Agent locally for text requests:

```powershell
.\.venv\Scripts\python.exe -m agents.pii_redaction.run_api
```

```powershell
$body = @{ input = 'Contact synthetic.user@example.test'; language = 'en' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/redact/text -ContentType application/json -Body $body
```

For local hosted-agent inspection, press **F5** in VS Code to start the Invocations host and open the Foundry Toolkit Agent Inspector.

## Use The Deployed Document Agent

This workflow requires:

- Azure CLI authenticated as an identity allowed to invoke the deployed Foundry agent.
- Azure Developer CLI (`azd`) with the deployed environment selected, unless you provide the endpoint explicitly.
- Network access to the deployed agent and any private endpoints required by your environment.

Place authorized files directly in [samples/input](samples/input). Do not place nested directories there. The standard executor processes one file at a time and writes the response to [samples/output](samples/output) using the same filename.

### Developer Access To Hosted Agents

A public agent endpoint is network-reachable but does not allow anonymous invocation. Every developer must authenticate with Microsoft Entra ID and have the **Foundry Agent Consumer** role. This is separate from the runtime identity permissions described below.

Use the narrowest appropriate scope:

- **One agent:** Assign the role at that agent's scope. This is the recommended option for developers who need only one endpoint.
- **All agents in this project:** Assign the role at the Foundry project scope.

A developer can assign this role to themselves only when they already have permission to create Azure role assignments, such as **Owner**, **User Access Administrator**, or **Role Based Access Control Administrator** at the applicable scope. Otherwise, an authorized administrator must run the command for them.

Authenticate and assign access to only the Document Redaction Agent:

```powershell
az login

$developerObjectId = az ad signed-in-user show --query id --output tsv
$projectScope = azd env get-value AZURE_AI_PROJECT_ID
$agentScope = "$projectScope/agents/document-redaction-agent"

az role assignment create `
  --assignee-object-id $developerObjectId `
  --assignee-principal-type User `
  --role "Foundry Agent Consumer" `
  --scope $agentScope `
  --output none
```

To allow the developer to invoke every hosted agent in this Foundry project, use the project scope instead:

```powershell
az role assignment create `
  --assignee-object-id $developerObjectId `
  --assignee-principal-type User `
  --role "Foundry Agent Consumer" `
  --scope $projectScope `
  --output none
```

Role assignments can take several minutes to propagate. The developer must run `az login` as the same identity before invoking an agent through the scripts in this repository. Do not grant **Owner** or **Contributor** merely to invoke an agent.

### PowerShell

The executor resolves the deployed endpoint from `--endpoint`, then from `AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT`, and finally from the currently selected `azd` environment. After `azd up`, no manual endpoint export is required as long as that environment remains selected.

If you need the complete active `responsibleai` environment in the current terminal, load it without printing endpoint values:

```powershell
$values = azd env get-values --environment responsibleai --output json |
    ConvertFrom-Json -AsHashtable

foreach ($item in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable(
        [string]$item.Key,
        [string]$item.Value,
        "Process"
    )
}
```

Redact one PDF and replace an existing output with the same name:

```powershell
.\.venv\Scripts\python.exe -m scripts.live_document_executor `
  --input-dir samples\input `
  --output-dir samples\output `
  --file synthetic-scanned-pii.pdf `
  --overwrite `
  --timeout-seconds 240
```

Redact one Word document:

```powershell
.\.venv\Scripts\python.exe -m scripts.live_document_executor `
  --input-dir samples\input `
  --output-dir samples\output `
  --file synthetic-pii-record.docx `
  --overwrite `
  --timeout-seconds 240
```

Redact every supported file in the input folder sequentially:

```powershell
.\.venv\Scripts\python.exe -m scripts.live_document_executor `
  --input-dir samples\input `
  --output-dir samples\output `
  --overwrite `
  --timeout-seconds 240
```

### Command Prompt

Authenticate with Azure CLI:

```cmd
az login
```

Run one file:

```cmd
.\.venv\Scripts\python.exe -m scripts.live_document_executor --input-dir samples\input --output-dir samples\output --file synthetic-scanned-pii.pdf --overwrite --timeout-seconds 240
```

Do not paste the endpoint into source files, scripts, issue comments, or logs.

### Input And Output Contract

- Maximum input size is 10 MB.
- Supported extensions are `.txt`, `.csv`, `.json`, `.xml`, `.md`, `.log`, `.docx`, and `.pdf`.
- The selected file must be directly inside the input folder.
- Existing outputs are protected unless `--overwrite` is supplied.
- The executor validates returned native PDF, DOCX, and TXT artifacts before replacing an output. A failed call or invalid native artifact leaves any existing output unchanged.
- Native source and output formats are preserved for `.txt`, `.pdf`, and `.docx`. Structured files are saved as redacted UTF-8 text.

### Direct HTTP Debug Runner

[scripts/debug_live_document_redactor.py](scripts/debug_live_document_redactor.py) is for a narrow live-agent diagnostic. It invokes exactly one `.pdf`, `.docx`, or `.txt` file and writes returned bytes without parsing the document. It resolves the endpoint from `--endpoint`, the process environment, or the selected `azd` environment, in that order. Use the standard executor for normal processing.

With the deployed `azd` environment selected, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.debug_live_document_redactor `
  --input samples\input\synthetic-scanned-pii.pdf `
  --output samples\output\synthetic-scanned-pii.response.pdf `
  --timeout-seconds 240
```

## Deploy Without a VNet

Create a new environment for public networking. Replace the tenant and subscription placeholders, then run these commands from the repository root:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"

azd auth logout
azd auth login --tenant-id "<tenant-id>" --use-device-code

azd env new "rai-public" `
  --location "eastus2" `
  --subscription "<subscription-id>" `
  --no-prompt

azd env set USE_VNET "false"
azd env set AI_LANGUAGE_SKU "S"
azd env set DOCUMENT_INTELLIGENCE_SKU "S0"
azd env set PII_CONFIDENCE_THRESHOLD "0.7"
azd env set PII_DEFAULT_LANGUAGE "en"

azd provision --preview
azd up --no-prompt

if ($LASTEXITCODE -eq 0) {
  $env:AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT = `
    azd env get-value AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT
}
```

After `azd up`, Bicep outputs and Foundry deployment outputs are persisted in the selected `azd` environment. The conditional block also loads the Document Redaction Agent endpoint into the current PowerShell process; child processes started from that terminal inherit it. The `postup` hooks configure hosted-agent RBAC and verify all required variable names without displaying their values; use `azd env get-values` to inspect them locally.

Use a fresh environment because Foundry network injection cannot be changed after account creation. The `S` and `S0` tiers incur usage charges. See [infra/README.md](infra/README.md#provision-without-a-vnet) for infrastructure-only deployment, retry steps, and enterprise Storage policy considerations.

### Agent Runtime RBAC

The Document Redaction Agent's hosted runtime identity requires these resource-scoped assignments after `azd deploy`:

| Resource | Built-in role | Purpose |
| --- | --- | --- |
| Azure AI Language | Cognitive Services User | Submit and poll native document PII jobs |
| Temporary document Storage account | Storage Blob Data Contributor | Upload source files and download/delete redacted artifacts |

The `postup` hooks configure these assignments. `Cognitive Services Language Reader` is not sufficient because it does not authorize the native `/language/analyze-documents/jobs` operation. See [infra/README.md](infra/README.md#post-deployment-agent-identity-rbac) for manual recovery commands and the complete specialist-agent RBAC matrix.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Set AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT` | Update the local checkout, select the deployed `azd` environment, or provide `--endpoint`. |
| `HTTP 401` or `HTTP 403` | Run `az login` with an identity authorized to invoke the hosted agent. |
| `HTTP 422` with `HTTP 401 (PermissionDenied)` | Rerun `azd up`, or load `azd env get-values` into the process and run `scripts/configure_agent_rbac.py`; then allow time for RBAC propagation. |
| `FileExistsError` | Use `--overwrite` or select a new output folder. |
| Invalid native document response | Preserve the prior output, inspect the hosted-agent trace, and do not rename text or JSON output as PDF/DOCX. |
| Cannot query traces | Verify Azure RBAC for telemetry query access and the configured Azure Monitor network path. |

## Further Documentation

For infrastructure operations, see [infra/README.md](infra/README.md) and [docs/deployment.md](docs/deployment.md). For the native document workflow, see [agents/document_redaction/README.md](agents/document_redaction/README.md) and [samples/README.md](samples/README.md).

## Contribution Requirements

Never commit real PII, credentials, service keys, tokens, SAS values, production prompts, or unredacted agent responses. Every detector, replacement policy, and overlap rule needs deterministic synthetic tests. Treat a redaction miss as more severe than conservative over-redaction, and measure both before production rollout.
