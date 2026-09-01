# Responsible AI and privacy controls

## Principles

- **Privacy and security:** data minimization, memory-only source processing, managed identity, private networking in production, and no sensitive telemetry.
- **Reliability and safety:** deterministic fallback, overlap resolution, fail-closed processing errors, size limits, and confidence thresholds.
- **Fairness:** evaluate recall by language, document type, identity format, geography, and image quality. Local regex is not a substitute for multilingual Azure AI Language models.
- **Transparency:** responses identify categories, confidence, source, and offsets but not original values. Consumers must disclose automated redaction.
- **Accountability:** version policy, preserve reviewer decisions, document residual risk, and assign service owners.
- **Inclusiveness:** test names, addresses, scripts, and formats across represented populations; provide accessible human-review experiences.

## Known limitations

- No PII system guarantees complete detection. Handwriting, low-resolution images, uncommon identity formats, and contextual identifiers can be missed.
- Generic local name/address patterns are intentionally conservative and label-dependent. Use hybrid mode for enterprise workloads.
- Image output supports raster images. PDF/DOCX content is returned as redacted extracted text in this implementation; format-preserving reconstruction is a roadmap item.
- Custom regex can cause catastrophic backtracking. Restrict authoring to trusted administrators and test expressions before production rollout.

## Human oversight

Route low-confidence, high-impact, regulated, or failed extraction cases to the planned Human Review Agent. Reviewers should see the minimum content required, have time-limited access, and never copy sensitive values into comments.
