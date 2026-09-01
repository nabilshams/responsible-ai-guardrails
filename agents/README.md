# Agent catalog

Each agent owns only hosting, request validation, and orchestration. Reusable policy and integrations belong in `shared/guardrails`.

| Agent | Status | Purpose |
| --- | --- | --- |
| PII Redaction | Implemented | Detect and remove sensitive text; burn OCR-aligned masks into images |
| PII Detection | Planned | Classify and locate PII without modifying content |
| Image Redaction | Planned | General visual-region and face redaction |
| Content Safety | Planned | Azure AI Content Safety policy enforcement |
| Prompt Injection Detection | Planned | Detect direct and indirect prompt attacks |
| Secret & Credential Detection | Planned | Detect keys, tokens, passwords, and connection strings |
| DLP Compliance | Planned | Apply tenant data-loss-prevention policies |
| Human Review | Planned | Risk-based review and approval queues |
| Audit & Compliance | Planned | Privacy-safe evidence, control mapping, and reporting |

New agents must implement versioned input/output contracts, use managed identity, emit privacy-safe telemetry, and include offline tests plus synthetic evaluation data.
