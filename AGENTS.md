# Agent development instructions

This project was built with the microsoft-foundry skill. Before working on or answering questions about Foundry agents, read the microsoft-foundry skill first. If you are in VS Code, read the vscode-microsoft-foundry skill first.

## Engineering rules

- Never log, persist, or include original sensitive values in responses, traces, exception messages, snapshots, or test artifacts.
- Keep guardrail policy in `shared/guardrails` and hosting adapters in `agents`.
- Default to `DefaultAzureCredential`; do not add shared keys or credentials to source control.
- All examples and evaluation fixtures must be visibly synthetic.
- Add deterministic unit tests for every detector, replacement policy, and overlap rule.
- Treat a redaction miss as higher severity than conservative over-redaction, while measuring both.
- Preserve current public contracts unless a versioned API is introduced.
