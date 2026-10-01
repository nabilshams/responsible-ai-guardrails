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
  B -->|Text| C[Text extraction]
  B -->|TXT, CSV, JSON, XML, MD, LOG| P[Structured text extraction]
  B -->|PDF, DOCX| D[Azure AI Language document-based PII]
  B -->|Image| E[Document Intelligence OCR and geometry]
  C --> F[Azure AI Language PII]
  P --> F
  C --> N[Deterministic secret detection]
  P --> N
  F --> G[Combined span normalization]
  N --> G
  G --> I[Redacted text]
  D --> Q[Layout-preserving native document]
  E --> R[Azure AI Language PII]
  R --> S[PII span normalization]
  S --> J[Opaque pixel masks]
  I --> K[Privacy-safe response]
  Q --> K
  J --> K
  K --> L[Application]
  K -. counts and correlation only .-> M[Application Insights / audit]
```

## Service selection

| Capability | Service | Rationale |
| --- | --- | --- |
| Contextual PII | Azure AI Language | Names, addresses, identity categories, multilingual models |
| Runtime and structured-text secrets | Deterministic local signatures and entropy checks | Redacts credentials without transmitting matched values |
| Structured-document PII | Azure AI Language text PII | Combines PII and secret spans in UTF-8 text-based files |
| Native document PII | Azure AI Language document-based PII | Redacts PDF and DOCX while preserving native layout |
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
emitting source values. Secret detection covers runtime text and structured UTF-8
documents; native PDF/DOCX and image transformations remain PII-only.
