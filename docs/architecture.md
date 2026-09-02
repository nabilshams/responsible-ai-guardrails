# Architecture

## Design goals

- Run deterministic protection before prompts reach generative models and after responses leave them.
- Keep original content in memory only and never place it in logs, traces, queues, or evaluation artifacts.
- Separate detection, policy, redaction transforms, hosting, and audit metadata.
- Use `DefaultAzureCredential` for local developer identity, workload identity, and managed identity.

## Request flow

```mermaid
flowchart LR
  A[Application] --> B{Specialist hosted agent}
  B -->|Text| C[PII Redaction Agent]
  B -->|TXT, PDF, DOCX| D[Azure AI Language document-based PII]
  B -->|Image| E[Document Intelligence OCR and geometry]
  C --> F[Azure AI Language PII]
  D --> I[Layout-preserving native document]
  E --> F
  F --> G[Span normalization]
  G --> H{Output transform}
  H -->|Text or document| I[Redacted text]
  H -->|Image| J[Opaque pixel masks]
  I --> K[Privacy-safe response]
  J --> K
  K --> L[Application]
  K -. counts and correlation only .-> M[Application Insights / audit]
```

## Service selection

| Capability | Service | Rationale |
| --- | --- | --- |
| Contextual PII | Azure AI Language | Names, addresses, identity categories, multilingual models |
| Native document PII | Azure AI Language document-based PII | Redacts TXT, PDF, and DOCX while preserving native layout |
| Document extraction and OCR geometry | Azure Document Intelligence | Locates image words for the Image Redaction Agent |
| Image PII masking | Document Intelligence + Azure AI Language | Maps detected PII spans back to irreversible pixel masks |
| General visual objects | Azure AI Vision | Planned extension for non-text objects and faces |
| Multimodal schema extraction | Azure AI Content Understanding | Planned complex document policies; keep behind an adapter |
| Harm categories | Azure AI Content Safety | Planned Content Safety and prompt-attack controls |
| Agent hosting and lifecycle | Microsoft Foundry | Managed hosted-agent runtime, identity, telemetry, and evaluation |

## Extension contract

New detectors implement `PiiDetector.detect()`. New redactors consume normalized `DetectedEntity` spans. Hosting adapters call the relevant shared service and must not duplicate policy or emit source values. The PII agent accepts text only; document and image transformations remain isolated in their own agents.
