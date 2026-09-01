# Deployment

## Local

1. Create `.venv` and install `requirements-dev.txt`.
2. Copy `.env.example` to `.env`.
3. Leave `PII_BACKEND=local` for offline tests, or configure Azure endpoints and use `hybrid`.
4. Press F5 to start the Invocations protocol host on port 8088 and open Agent Inspector.
5. Run `python -m agents.pii_redaction.run_api` for the optional REST adapter on port 8000.

## Azure preparation

The repository targets a new Microsoft Foundry project through `azure.yaml`; no resources were provisioned during scaffolding. Configure an azd environment with subscription, region, Azure AI Language endpoint, and Document Intelligence endpoint. Assign the hosted agent's managed identity data-plane access to those resources.

Use separate Azure AI resources and managed identities per specialist guardrail in production. Do not reuse unrelated Search or model resources. Apply private endpoints and diagnostic settings before handling production data.

## CI/CD

The CI workflow runs linting, type checks, tests, dependency audit, and static security analysis. The deployment workflow uses GitHub OIDC and protected environment variables; it contains no client secret. Require approvals for production environments and validate evaluation gates before deployment.

## Invocation payloads

Text:

```json
{"input":"Contact synthetic.user@example.test","language":"en"}
```

Document or image:

```json
{
  "document": {
    "content_base64": "<base64>",
    "content_type": "image/png",
    "filename": "synthetic.png"
  },
  "language": "en"
}
```

The response streams a JSON object containing redacted text, entity metadata without values, and—for raster images—a base64-encoded redacted PNG.
