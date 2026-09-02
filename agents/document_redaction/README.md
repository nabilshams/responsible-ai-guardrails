# Document Redaction Agent

Uses the Azure AI Language document-based PII API to redact `.txt`, `.pdf`, and `.docx` files while preserving their native structure and formatting. The response contains the redacted native file as base64, its media type, filename, and correlation ID.

Service overview: [Document-based PII overview](https://learn.microsoft.com/azure/ai-services/language-service/personally-identifiable-information/document-based-pii-overview).

The service requires temporary private Blob source and target containers. The agent uploads a randomized source blob, submits the asynchronous `2026-05-01` document PII job using managed identity, downloads the resulting native document, and attempts to delete all temporary artifacts before responding. A one-day storage lifecycle rule provides cleanup defense in depth.

Structured UTF-8 `.csv`, `.json`, `.xml`, `.md`, and `.log` files retain the existing extracted-text redaction path because the native document API supports only TXT, PDF, and DOCX.

Input uses a `document` object with synthetic or authorized `content_base64`, `content_type`, and `filename` fields. Original content is never logged; native documents exist only as temporary private processing blobs and are deleted after the job.
