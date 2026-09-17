"""Minimal authenticated client for live Foundry Invocations agents."""

from __future__ import annotations

import json
from typing import Any

import httpx
from azure.core.credentials import TokenCredential


class LiveAgentInvocationError(RuntimeError):
    """Raised when a live hosted-agent invocation fails safely."""


def _safe_agent_error(response: httpx.Response) -> str:
    """Return only the agent's allowlisted structured error fields."""
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    code = payload.get("error")
    message = payload.get("message")
    safe_parts = [value.strip() for value in (code, message) if isinstance(value, str)]
    return ": ".join(part for part in safe_parts if part)


class LiveAgentClient:
    """Invoke one deployed Invocations endpoint with Microsoft Entra credentials."""

    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential,
        *,
        timeout_seconds: float = 180.0,
    ) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("The live agent endpoint must use HTTPS")
        self._endpoint = endpoint
        self._credential = credential
        self._timeout_seconds = timeout_seconds

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        token = self._credential.get_token("https://ai.azure.com/.default").token
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            response.raise_for_status()
            return parse_invocation_response(response)
        except httpx.HTTPStatusError as exc:
            detail = _safe_agent_error(exc.response)
            suffix = f" ({detail})" if detail else ""
            raise LiveAgentInvocationError(
                "Live hosted-agent invocation failed with HTTP "
                f"{exc.response.status_code}{suffix}"
            ) from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise LiveAgentInvocationError("Live hosted-agent invocation failed") from exc


def parse_invocation_response(response: httpx.Response) -> dict[str, Any]:
    """Return an agent JSON response or the final payload from an SSE stream."""
    content_type = response.headers.get("content-type", "").casefold()
    if "application/json" in content_type:
        value = response.json()
        if not isinstance(value, dict):
            raise LiveAgentInvocationError("Live agent returned invalid JSON")
        return value

    final_text: str | None = None
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        if isinstance(event, dict) and event.get("type") == "done":
            value = event.get("full_text")
            if isinstance(value, str):
                final_text = value
    if final_text is None:
        raise LiveAgentInvocationError("Live agent returned no completion event")

    result = json.loads(final_text)
    if not isinstance(result, dict):
        raise LiveAgentInvocationError("Live agent returned an invalid completion")
    return result
