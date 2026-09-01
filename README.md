# responsible-ai-guardrails

A collection of reusable Responsible AI guardrails and agents for detecting, redacting, governing, and protecting sensitive information across documents, images, conversations, and AI workflows.

## Repository structure

- `agents/`
- `shared/guardrails/`
- `shared/evaluations/`
- `tests/`
- `docs/`
- `sample_data/`

## Implemented now

- `PIIRedactionAgent`: detects and redacts names, emails, phone numbers, addresses, driver licence numbers, passport numbers, credit card numbers, tax identifiers, and custom sensitive patterns.
- `PIIDetectionAgent`: detection-only companion agent.

## Planned next agents

- Image Redaction Agent
- Content Safety Agent
- Prompt Injection Detection Agent
- Secret & Credential Detection Agent
- DLP Compliance Agent
- Human Review Agent
- Audit & Compliance Agent

See `docs/architecture.md` and `docs/pii-redaction-agent.md`.
