# Secret & Credential Detection Agent

Deterministically detects and redacts runtime credentials in text without invoking a
model or transmitting detected values to a provider. It combines high-confidence
structural signatures with context and entropy checks for generic assignments.

The version `1.0` Invocations contract accepts `input` or `message` and returns
redacted text, safe entity metadata, category counts, and a correlation ID. Original
values are never included in responses, logs, traces, or validation calls.
