# Evaluation

The baseline suite is deterministic and uses visibly synthetic data only. It measures exact-span precision, recall, F1, redaction completeness, sensitive-value leakage, and negative-example preservation.

## Run

1. Create a Python 3.11+ virtual environment.
2. Install `requirements-dev.txt`.
3. Run tests from VS Code Test Explorer or run `pytest`.

The seed data is in `shared/evaluations/datasets/pii_redaction.jsonl`. Add languages, identity formats, OCR qualities, and document types before production. Never copy production PII into evaluation data.

## Release gates

| Metric | Initial gate |
| --- | ---: |
| Recall for high-impact identifiers | 0.99 |
| Overall span recall | 0.95 |
| Overall span precision | 0.90 |
| Sensitive-value leakage | 0 |
| Negative text preservation | 0.98 |
| Image sensitive-region coverage | 1.00 |

Track metrics by entity type and cohort; aggregate scores can hide harmful misses. Any regression in credit cards, tax IDs, passports, driver licences, or tenant custom patterns blocks release.

Foundry remote evaluation can be added after deployment. Keep deterministic privacy metrics as the release authority; an LLM judge is not required to determine whether a sensitive value remains.
