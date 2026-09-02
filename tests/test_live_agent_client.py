from __future__ import annotations

import json

import httpx
import pytest

from scripts.live_agent_client import (
    LiveAgentClient,
    LiveAgentInvocationError,
    parse_invocation_response,
)


class StubCredential:
    def get_token(self, *scopes: str, **kwargs: object) -> object:
        del scopes, kwargs
        return type("Token", (), {"token": "synthetic-token"})()


def test_parses_json_response() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"redacted_text": "Synthetic [EMAIL]"},
    )

    assert parse_invocation_response(response)["redacted_text"] == "Synthetic [EMAIL]"


def test_parses_final_sse_response() -> None:
    result = json.dumps({"redacted_text": "Synthetic [EMAIL]"})
    event = json.dumps({"type": "done", "full_text": result})
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=f"data: {event}\n\n",
    )

    assert parse_invocation_response(response)["redacted_text"] == "Synthetic [EMAIL]"


def test_rejects_sse_without_completion() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='data: {"type":"token","content":"synthetic"}\n\n',
    )

    with pytest.raises(LiveAgentInvocationError, match="no completion"):
        parse_invocation_response(response)


@pytest.mark.asyncio
async def test_http_error_surfaces_only_allowlisted_agent_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.Response(
        422,
        json={
            "error": "processing_failed",
            "message": "Azure AI Language returned an invalid PDF artifact",
            "sensitive": "must-not-appear",
        },
        request=httpx.Request("POST", "https://synthetic.example.test"),
    )

    async def post(*args: object, **kwargs: object) -> httpx.Response:
        del args, kwargs
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    client = LiveAgentClient(
        "https://synthetic.example.test",
        StubCredential(),  # type: ignore[arg-type]
    )

    with pytest.raises(LiveAgentInvocationError) as captured:
        await client.invoke({"synthetic": True})

    diagnostic = str(captured.value)
    assert "processing_failed" in diagnostic
    assert "invalid PDF artifact" in diagnostic
    assert "must-not-appear" not in diagnostic
