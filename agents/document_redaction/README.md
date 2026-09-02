# Document Redaction Agent

Extracts text from supported documents, detects PII with Azure AI Language, and returns redacted text. It does not claim to rewrite the original PDF or Office binary.

UTF-8 text formats are processed directly: `.txt`, `.csv`, `.json`, `.xml`, `.md`, and `.log`. Other supported document formats, including PDFs and Office documents, are extracted with Azure Document Intelligence.

Input uses a `document` object with synthetic or authorized `content_base64`, `content_type`, and `filename` fields. Original content is never logged or persisted.
