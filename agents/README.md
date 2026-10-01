# Agent catalog

Each agent owns only hosting, request validation, and orchestration. Reusable policy and integrations belong in `shared/guardrails`.

| Agent | Status | Purpose |
| --- | --- | --- |
| PII Redaction | Implemented | Detect and remove sensitive text using Azure AI Language only |
| Document Redaction | Implemented | Preserve native TXT, PDF, and DOCX layout with Azure AI Language document-based PII |
| Image Redaction | Implemented | OCR images and burn PII-aligned masks into output pixels |
| Secret & Credential Detection | Implemented | Detect and redact runtime text credentials not protected by repository secret scanning |

New agents must implement versioned input/output contracts, use managed identity, emit privacy-safe telemetry, and include offline tests plus synthetic evaluation data.

## Microsoft-native controls and integrations

The following capabilities are platform integrations rather than standalone hosted
agents:

| Capability | Microsoft service | Project responsibility |
| --- | --- | --- |
| PII detection | Azure AI Language and Microsoft Foundry PII guardrails | Expose safe detection metadata through the existing redaction services when required |
| Content safety | Microsoft Foundry Guardrails and Azure AI Content Safety | Configure severity thresholds, intervention points, and evaluations |
| Prompt injection protection | Microsoft Foundry Prompt Shields | Configure user and indirect attack controls and test application trust boundaries |
| Data loss prevention | Microsoft Purview DLP and Information Protection | Integrate classifications and policies with application destination context |
| Human review | Power Automate Approvals, Dataverse, Teams, and Microsoft Entra ID | Submit sanitized review requests and process approval decisions |
| Audit and compliance | Microsoft Foundry observability, Application Insights, Azure Monitor, and Microsoft Purview Audit | Emit privacy-safe policy and decision telemetry |
