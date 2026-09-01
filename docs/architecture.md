# Responsible AI Guardrails Architecture

This repository is organized to support modular Responsible AI agents and guardrails:

- `agents/`: agent implementations and stubs
- `shared/guardrails/`: reusable guardrail logic and service abstractions
- `shared/evaluations/`: dataset loader and evaluation fixtures
- `tests/`: unit tests
- `docs/`: architecture and implementation notes
- `sample_data/`: sample inputs for local validation

## Current implementation

- `PIIRedactionAgent` provides document/prompt/response/OCR-text PII detection and redaction.
- `PIIDetectionAgent` provides detection-only behavior.

## Planned agents

- Image Redaction Agent
- Content Safety Agent
- Prompt Injection Detection Agent
- Secret & Credential Detection Agent
- DLP Compliance Agent
- Human Review Agent
- Audit & Compliance Agent

## Azure integration path

The `shared/guardrails/service_clients.py` module provides the abstraction point for integrating:

- Azure AI Foundry
- Azure AI Language
- Azure AI Vision
- Azure AI Content Understanding
- Azure Document Intelligence
