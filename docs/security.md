# Security and threat model

## Trust boundaries

1. The calling application authenticates to the hosted agent or API through Microsoft Entra ID and private networking.
2. The workload uses managed identity to call Azure AI Language.
3. Original source content stays inside the processing boundary. Native document PII uses short-lived private Blob artifacts that are deleted after processing, with a one-day lifecycle rule as cleanup defense in depth.
4. Telemetry contains correlation ID, category names, counts, latency, and status only.

## Required production controls

- Disable public network access where supported and use private endpoints, private DNS, and egress allowlists.
- Assign only Cognitive Services User/data-plane roles required by each specialist identity.
- Authenticate the REST adapter at the gateway or hosting layer; never expose it directly to the internet.
- Store configuration in App Configuration and secrets in Key Vault. Prefer identity over keys.
- Rate-limit by tenant and identity, and cap request size and processing time.
- Encrypt storage with customer-managed keys when required. Document PII storage disables shared-key and public blob access, permits Azure trusted-service access for the Language resource, and exposes Blob privately to the hosted agent VNet.
- Pin and scan dependencies, produce an SBOM, sign deployment artifacts, and protect deployment environments.

## Abuse cases

| Threat | Control |
| --- | --- |
| Sensitive content in logs | Structured metadata-only logging; tests assert no detected value is logged |
| Regex denial of service | Pattern length limits, trusted administrators, review, and future timeout-capable regex engine |
| Overlapping spans leak values | Confidence-ranked normalization and reverse-order replacement |
| Identity key leakage | `DefaultAzureCredential`; no key settings or connection strings in source |
| Cross-tenant policy confusion | Dedicated policy/version per tenant and tenant-bound identity in production |
