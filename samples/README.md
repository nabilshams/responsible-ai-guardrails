# Live document test executor

Place only visibly synthetic test files in `samples/input`. Supported extensions are `.txt`, `.csv`, `.json`, `.xml`, `.md`, `.log`, `.docx`, and `.pdf`. Text files must use UTF-8; Word and PDF files use Azure AI Language document-based PII redaction.

The repository includes synthetic fixtures for every supported format. Together they exercise names, reserved `example.test` email addresses, fictional `555` phone numbers, placeholder addresses, synthetic identifiers, payment test numbers, and documentation-reserved IP ranges.

The executor sends files to the deployed Document Redaction Agent sequentially and writes each redacted response to `samples/output` with the same filename. TXT, PDF, and DOCX outputs retain their native format; other supported formats contain redacted UTF-8 text. Input and output files are ignored by Git to prevent accidental persistence of test content.

Authenticate with Azure CLI or another `DefaultAzureCredential` source, then set `AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT` to the full deployed Invocations endpoint.

Run all files:

```powershell
python -m scripts.live_document_executor
```

Run one file:

```powershell
python -m scripts.live_document_executor --file synthetic.txt
```

Existing outputs are not replaced unless `--overwrite` is supplied. The tool emits only a processed-file count and does not log filenames or file contents.
