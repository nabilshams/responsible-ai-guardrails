# Document Redaction Agent

Uses the Azure AI Language document-based PII API to redact `.pdf` and `.docx` files while preserving their native structure and formatting. The response contains the redacted native file as base64, its media type, filename, and correlation ID.

Service overview: [Document-based PII overview](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/document-based-pii-overview).

The service requires temporary private Blob source and target containers. The agent uploads a randomized source blob, submits the asynchronous `2026-05-01` document PII job using managed identity, downloads the resulting native document, and attempts to delete all temporary artifacts before responding. A one-day storage lifecycle rule provides cleanup defense in depth.

Plain-text `.txt` and structured UTF-8 `.csv`, `.json`, `.xml`, `.md`, and `.log` files use the extracted-text redaction path because the native document API supports only PDF and DOCX.

Input uses a `document` object with synthetic or authorized `content_base64`, `content_type`, and `filename` fields. Original content is never logged; native documents exist only as temporary private processing blobs and are deleted after the job.

## Custom words and phrases

Add `"custom_terms": ["Project Falcon", "Contoso"]` (up to 100 terms, 256 characters each) to the invocation body. Matching is case-insensitive on word boundaries, repeats are all redacted, and phrases may span words or line breaks.

- **PDF**: when `custom_terms` is supplied, Azure AI Document Intelligence locates each match (together with Azure AI Language PII and secrets) on its page, and the underlying text is removed from the PDF. Without `custom_terms`, the Azure AI Language native PDF path is unchanged.
- **Text files** (`.txt`, `.csv`, …): custom terms are added to the structured-text redaction.
- **DOCX**: custom terms are rejected with a 400 error because they cannot be applied safely.
