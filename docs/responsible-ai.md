# Responsible AI and privacy controls

## Principles

- **Privacy and security:** data minimization, memory-only source processing, managed identity, private networking in production, and no sensitive telemetry.
- **Reliability and safety:** Azure AI Language errors fail closed; overlap resolution, size limits, and confidence thresholds are deterministic.
- **Fairness:** evaluate recall by language, identity format, and geography across Azure AI Language-supported categories.
- **Transparency:** responses identify categories, confidence, source, and offsets but not original values. Consumers must disclose automated redaction.
- **Accountability:** version policy, preserve reviewer decisions, document residual risk, and assign service owners.
- **Inclusiveness:** test names, addresses, scripts, and formats across represented populations; provide accessible human-review experiences.

## Known limitations

- No PII system guarantees complete detection. Uncommon identity formats and contextual identifiers can be missed.
- The agent accepts text only; document extraction and image redaction belong to separate specialist agents.

## Human oversight

Route low-confidence, high-impact, regulated, or failed analysis cases to the planned Human Review Agent. Reviewers should see the minimum content required, have time-limited access, and never copy sensitive values into comments.
