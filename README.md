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

## Security Model

- Azure AI Language is the PII detection and redaction service. This solution does not send document content to a generative model.
- Authentication uses `DefaultAzureCredential`; do not add Azure service keys, connection strings, SAS tokens, or production PII to source control.
- Keep source files and generated outputs outside Git. Supplied sample files are visibly synthetic only.
- The deployed Document Redaction Agent returns native document bytes as base64 over the Invocations protocol. The executor decodes them and writes the result to disk.
- Privacy-safe application logs must not contain original or redacted document content.

## Prerequisites

- Python 3.11 or newer. The hosted-agent configuration uses Python 3.13.
- Azure CLI authenticated as an identity allowed to invoke the deployed Foundry agent.
- Azure Developer CLI (`azd`) with the `responsibleai` environment already provisioned and deployed.
- Network access to the deployed agent and any private endpoints required by your environment.

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

## Redact Documents With The Deployed Agent

Place authorized files directly in [samples/input](samples/input). Do not place nested directories there. The standard executor processes one file at a time and writes the response to [samples/output](samples/output) using the same filename.

### PowerShell

Load the active `responsibleai` environment into the current terminal without printing endpoint values:

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
.\.venv\Scripts\python.exe scripts\live_document_executor.py `
  --input-dir samples\input `
  --output-dir samples\output `
  --file synthetic-scanned-pii.pdf `
  --overwrite `
  --timeout-seconds 240
```

Redact one Word document:

```powershell
.\.venv\Scripts\python.exe scripts\live_document_executor.py `
  --input-dir samples\input `
  --output-dir samples\output `
  --file synthetic-pii-record.docx `
  --overwrite `
  --timeout-seconds 240
```

Redact every supported file in the input folder sequentially:

```powershell
.\.venv\Scripts\python.exe scripts\live_document_executor.py `
  --input-dir samples\input `
  --output-dir samples\output `
  --overwrite `
  --timeout-seconds 240
```

### Command Prompt

Authenticate, then set the full deployed Invocations endpoint in the current `cmd.exe` window:

```cmd
az login
set AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT=<deployed-invocations-endpoint>
```

Run one file:

```cmd
.\.venv\Scripts\python.exe scripts\live_document_executor.py --input-dir samples\input --output-dir samples\output --file synthetic-scanned-pii.pdf --overwrite --timeout-seconds 240
```

Do not paste the endpoint into source files, scripts, issue comments, or logs.

### Input And Output Contract

- Maximum input size is 10 MB.
- Supported extensions are `.txt`, `.csv`, `.json`, `.xml`, `.md`, `.log`, `.docx`, and `.pdf`.
- The selected file must be directly inside the input folder.
- Existing outputs are protected unless `--overwrite` is supplied.
- The executor validates returned native PDF, DOCX, and TXT artifacts before replacing an output. A failed call or invalid native artifact leaves any existing output unchanged.
- Native source and output formats are preserved for `.txt`, `.pdf`, and `.docx`. Structured files are saved as redacted UTF-8 text.

## Direct HTTP Debug Runner

[scripts/debug_live_document_redactor.py](scripts/debug_live_document_redactor.py) is for a narrow live-agent diagnostic. It invokes exactly one `.pdf`, `.docx`, or `.txt` file and writes returned bytes without parsing the document. Use the standard executor for normal processing.

After loading the environment in PowerShell, run:

```powershell
.\.venv\Scripts\python.exe scripts\debug_live_document_redactor.py `
  --input samples\input\synthetic-scanned-pii.pdf `
  --output samples\output\synthetic-scanned-pii.response.pdf `
  --timeout-seconds 240
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Set AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT` | Load the `responsibleai` azd environment or provide `--endpoint`. |
| `HTTP 401` or `HTTP 403` | Run `az login` with an identity authorized to invoke the hosted agent. |
| `HTTP 422` | The hosted agent received the request but Azure AI Language document processing did not complete. Review the agent trace and verify Language and Storage managed-identity access. |
| `FileExistsError` | Use `--overwrite` or select a new output folder. |
| Invalid native document response | Preserve the prior output, inspect the hosted-agent trace, and do not rename text or JSON output as PDF/DOCX. |
| Cannot query traces | Verify Azure RBAC for telemetry query access and the configured Azure Monitor network path. |

## Local Text API

The PII Redaction Agent can run locally for text requests:

```powershell
.\.venv\Scripts\python.exe -m agents.pii_redaction.run_api
```

```powershell
$body = @{ input = 'Contact synthetic.user@example.test'; language = 'en' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/redact/text -ContentType application/json -Body $body
```

For local hosted-agent inspection, press **F5** in VS Code to start the Invocations host and open the Foundry Toolkit Agent Inspector.

## Architecture And Deployment

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

For infrastructure operations, see [infra/README.md](infra/README.md) and [docs/deployment.md](docs/deployment.md). For the native document workflow, see [agents/document_redaction/README.md](agents/document_redaction/README.md) and [samples/README.md](samples/README.md).

## Contribution Requirements

Never commit real PII, credentials, service keys, tokens, SAS values, production prompts, or unredacted agent responses. Every detector, replacement policy, and overlap rule needs deterministic synthetic tests. Treat a redaction miss as more severe than conservative over-redaction, and measure both before production rollout.
