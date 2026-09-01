# Security and threat model

## Trust boundaries

1. The calling application authenticates to the hosted agent or API through Microsoft Entra ID and private networking.
2. The workload uses managed identity to call Azure AI Language and Document Intelligence.
3. Original source content stays inside the processing boundary and is discarded after the response.
4. Telemetry contains correlation ID, category names, counts, latency, and status only.

## Required production controls

- Disable public network access where supported and use private endpoints, private DNS, and egress allowlists.
- Assign only Cognitive Services User/data-plane roles required by each specialist identity.
- Authenticate the REST adapter at the gateway or hosting layer; never expose it directly to the internet.
- Store configuration in App Configuration and secrets in Key Vault. Prefer identity over keys.
- Enforce malware scanning before document processing and verify MIME type from content, not only client headers.
- Rate-limit by tenant and identity, cap request size and processing time, and reject encrypted or malformed documents.
- Encrypt storage and queues with customer-managed keys when required. The initial implementation does not persist input.
- Pin and scan dependencies, produce an SBOM, sign deployment artifacts, and protect deployment environments.

## Abuse cases

| Threat | Control |
| --- | --- |
| Sensitive content in logs | Structured metadata-only logging; tests assert no detected value is logged |
| Regex denial of service | Pattern length limits, trusted administrators, review, and future timeout-capable regex engine |
| Image decompression bomb | Upload limit plus Pillow limits; add decoded-pixel limits at the gateway |
| Overlapping spans leak values | Confidence-ranked normalization and reverse-order replacement |
| Identity key leakage | `DefaultAzureCredential`; no key settings or connection strings in source |
| Bypass through unsupported file | Fail closed with an explicit unsupported-document error |
| Cross-tenant policy confusion | Dedicated policy/version per tenant and tenant-bound identity in production |
