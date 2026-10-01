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
  H -->|Text| N[Secret Detection Agent]
  N --> O[Secret span normalization and redaction]
  O --> I[Redacted text]
  H -->|Document| I
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
| Runtime text secrets | Deterministic local signatures and entropy checks | Redacts credentials without transmitting matched values |
| Native document PII | Azure AI Language document-based PII | Redacts TXT, PDF, and DOCX while preserving native layout |
| Document extraction and OCR geometry | Azure Document Intelligence | Locates image words for the Image Redaction Agent |
| Image PII masking | Document Intelligence + Azure AI Language | Maps detected PII spans back to irreversible pixel masks |
| General visual objects | Azure AI Vision | Planned extension for non-text objects and faces |
| Multimodal schema extraction | Azure AI Content Understanding | Planned complex document policies; keep behind an adapter |
| Harm categories and prompt attacks | Microsoft Foundry Guardrails and Azure AI Content Safety | Platform controls configured on models and agents |
| Agent hosting and lifecycle | Microsoft Foundry | Managed hosted-agent runtime, identity, telemetry, and evaluation |

## Extension contract

PII detectors implement `PiiDetector.detect()`. Deterministic secret detectors return
the same internal `DetectedEntity` spans. Redactors consume normalized spans, and
hosting adapters call the relevant shared service without duplicating policy or
emitting source values. Secret detection currently covers runtime text only;
document and image transformations remain isolated in their own agents.
