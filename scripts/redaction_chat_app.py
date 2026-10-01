"""Local web API for PII, secret, document, and image redaction agents."""

from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from scripts.live_agent_client import LiveAgentClient, LiveAgentInvocationError, resolve_endpoint
from shared.guardrails.native_document_pii import validate_native_document

_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_FILES = 10
_WEB_ROOT = Path(__file__).resolve().parents[1] / "web"

_TEXT_ENDPOINT = "AGENT_PII_REDACTION_AGENT_INVOCATIONS_ENDPOINT"
_CREDENTIAL_REDACTION_ENDPOINT = "AGENT_SECRET_DETECTION_AGENT_INVOCATIONS_ENDPOINT"
_DOCUMENT_ENDPOINT = "AGENT_DOCUMENT_REDACTION_AGENT_INVOCATIONS_ENDPOINT"
_IMAGE_ENDPOINT = "AGENT_IMAGE_REDACTION_AGENT_INVOCATIONS_ENDPOINT"

_DOCUMENT_TYPES = {
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".md": "text/markdown",
    ".log": "application/octet-stream",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

_SAMPLES_ROOT = Path(__file__).resolve().parents[1] / "samples" / "input"
_SAMPLES: tuple[dict[str, str], ...] = (
    {
        "id": "text",
        "label": "PII text",
        "kind": "text",
        "filename": "synthetic-contact.txt",
        "media_type": "text/plain",
    },
    {
        "id": "secrets",
        "label": "Secrets text",
        "kind": "text",
        "filename": "synthetic-secrets.txt",
        "media_type": "text/plain",
    },
    {
        "id": "txt",
        "label": "Mixed · TXT",
        "kind": "file",
        "filename": "synthetic-mixed.txt",
        "media_type": "text/plain",
    },
    {
        "id": "csv",
        "label": "Mixed · CSV",
        "kind": "file",
        "filename": "synthetic-contacts.csv",
        "media_type": "text/csv",
    },
    {
        "id": "json",
        "label": "Mixed · JSON",
        "kind": "file",
        "filename": "synthetic-profile.json",
        "media_type": "application/json",
    },
    {
        "id": "docx",
        "label": "Record · DOCX",
        "kind": "file",
        "filename": "synthetic-pii-record.docx",
        "media_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    },
    {
        "id": "pdf",
        "label": "Form · PDF",
        "kind": "file",
        "filename": "synthetic-pii-form.pdf",
        "media_type": "application/pdf",
    },
)
_SAMPLES_BY_ID = {sample["id"]: sample for sample in _SAMPLES}


class AgentClient(Protocol):
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class AttachmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class RedactionChatRequest(BaseModel):
    message: str = Field(default="", max_length=100_000)
    language: str = Field(default="en", min_length=2, max_length=12)
    files: list[AttachmentRequest] = Field(default_factory=list, max_length=_MAX_FILES)


class RedactedFile(BaseModel):
    download_name: str
    content_type: str
    content_base64: str
    entity_counts: dict[str, int] = Field(default_factory=dict)


class RedactionChatResponse(BaseModel):
    redacted_text: str | None = None
    text_entity_counts: dict[str, int] = Field(default_factory=dict)
    files: list[RedactedFile] = Field(default_factory=list)


ClientProvider = Callable[[str], AgentClient]


class RedactionChatService:
    """Route local web requests to deployed specialist agents."""

    def __init__(self, client_provider: ClientProvider | None = None) -> None:
        self._credential: DefaultAzureCredential | None = None
        self._clients: dict[str, AgentClient] = {}
        self._client_provider: ClientProvider
        if client_provider is None:
            self._credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
            )

            def create_client(variable_name: str) -> AgentClient:
                assert self._credential is not None
                return LiveAgentClient(resolve_endpoint(variable_name), self._credential)

            self._client_provider = create_client
        else:
            self._client_provider = client_provider

    def close(self) -> None:
        if self._credential is not None:
            self._credential.close()

    def _client(self, variable_name: str) -> AgentClient:
        if variable_name not in self._clients:
            self._clients[variable_name] = self._client_provider(variable_name)
        return self._clients[variable_name]

    async def redact(self, request: RedactionChatRequest) -> RedactionChatResponse:
        if not request.message.strip() and not request.files:
            raise ValueError("Provide text or at least one supported file")
        redacted_text: str | None = None
        text_counts: dict[str, int] = {}
        if request.message.strip():
            pii_result = await self._client(_TEXT_ENDPOINT).invoke(
                {"message": request.message, "language": request.language},
            )
            pii_redacted_text = _required_string(pii_result, "redacted_text")
            secret_result = await self._client(_CREDENTIAL_REDACTION_ENDPOINT).invoke(
                {"contract_version": "1.0", "input": pii_redacted_text},
            )
            redacted_text = _required_string(secret_result, "redacted_text")
            text_counts = _merge_entity_counts(
                _entity_counts(pii_result),
                _entity_counts(secret_result),
            )

        redacted_files = []
        for index, attachment in enumerate(request.files, start=1):
            redacted_files.append(
                await self._redact_file(attachment, index, request.language),
            )

        return RedactionChatResponse(
            redacted_text=redacted_text,
            text_entity_counts=text_counts,
            files=redacted_files,
        )

    async def _redact_file(
        self,
        attachment: AttachmentRequest,
        index: int,
        language: str,
    ) -> RedactedFile:
        suffix = Path(attachment.name).suffix.casefold()
        content = _decode_file(attachment.content_base64)
        generic_name = f"upload-{index}{suffix}"
        download_name = f"redacted-{index}{'.png' if suffix in _IMAGE_TYPES else suffix}"

        if suffix in _DOCUMENT_TYPES:
            content_type = _DOCUMENT_TYPES[suffix]
            result = await self._client(_DOCUMENT_ENDPOINT).invoke(
                {
                    "document": {
                        "content_base64": base64.b64encode(content).decode("ascii"),
                        "content_type": content_type,
                        "filename": generic_name,
                    },
                    "language": language,
                },
            )
            encoded = result.get("redacted_document_base64")
            if isinstance(encoded, str):
                decoded = _decode_agent_file(encoded)
                validate_native_document(decoded, suffix)
            else:
                redacted = _required_string(result, "redacted_text")
                encoded = base64.b64encode(redacted.encode("utf-8")).decode("ascii")
            return RedactedFile(
                download_name=download_name,
                content_type=content_type,
                content_base64=encoded,
                entity_counts=_entity_counts(result),
            )

        if suffix in _IMAGE_TYPES:
            result = await self._client(_IMAGE_ENDPOINT).invoke(
                {
                    "image": {
                        "content_base64": base64.b64encode(content).decode("ascii"),
                        "content_type": _IMAGE_TYPES[suffix],
                        "filename": generic_name,
                    },
                    "language": language,
                },
            )
            encoded = _required_string(result, "redacted_image_base64")
            _validate_png(_decode_agent_file(encoded))
            return RedactedFile(
                download_name=download_name,
                content_type="image/png",
                content_base64=encoded,
                entity_counts=_entity_counts(result),
            )

        raise ValueError("A selected file type is not supported")


def _decode_file(encoded: str) -> bytes:
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("A selected file is not valid base64") from exc
    if not content:
        raise ValueError("Selected files cannot be empty")
    if len(content) > _MAX_FILE_BYTES:
        raise ValueError("A selected file exceeds the 10 MB limit")
    return content


def _decode_agent_file(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("A redaction agent returned an invalid file") from exc


def _validate_png(content: bytes) -> None:
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            if image.format != "PNG":
                raise ValueError("The redaction agent did not return a PNG")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RuntimeError("The image agent returned an invalid PNG") from exc


def _required_string(result: dict[str, Any], key: str) -> str:
    value = result.get(key)
    if not isinstance(value, str):
        raise RuntimeError("A redaction agent returned an invalid response")
    return value


def _entity_counts(result: dict[str, Any]) -> dict[str, int]:
    counts = result.get("entity_counts")
    if not isinstance(counts, dict):
        return {}
    return {
        key: value
        for key, value in counts.items()
        if isinstance(key, str) and isinstance(value, int) and value >= 0
    }


def _merge_entity_counts(*counts: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for group in counts:
        for category, count in group.items():
            merged[category] = merged.get(category, 0) + count
    return dict(sorted(merged.items()))


def create_app(service: RedactionChatService | None = None) -> FastAPI:
    chat_service = service or RedactionChatService()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        chat_service.close()

    application = FastAPI(
        title="Redaction Chat",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(
        _: Request,
        __: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "The request format is invalid"},
        )

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_WEB_ROOT / "redaction-chat.html")

    @application.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    @application.get("/api/samples", include_in_schema=False)
    def list_samples() -> JSONResponse:
        items: list[dict[str, str | bool]] = []
        for sample in _SAMPLES:
            entry: dict[str, str | bool] = {
                "id": sample["id"],
                "label": sample["label"],
                "kind": sample["kind"],
                "filename": sample["filename"],
                "previewable": sample["media_type"] == "application/pdf",
            }
            if sample["kind"] == "text":
                try:
                    entry["text"] = (_SAMPLES_ROOT / sample["filename"]).read_text(
                        encoding="utf-8"
                    )
                except OSError:
                    continue
            items.append(entry)
        return JSONResponse(content=items)

    @application.get("/api/samples/{sample_id}", include_in_schema=False)
    def get_sample(sample_id: str) -> FileResponse:
        sample = _SAMPLES_BY_ID.get(sample_id)
        if sample is None or sample["kind"] != "file":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown sample")
        path = _SAMPLES_ROOT / sample["filename"]
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")
        return FileResponse(
            path,
            media_type=sample["media_type"],
            filename=sample["filename"],
            content_disposition_type="inline",
        )

    @application.post("/api/redact", response_model=RedactionChatResponse)
    async def redact(request: RedactionChatRequest) -> RedactionChatResponse:
        try:
            return await chat_service.redact(request)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except (LiveAgentInvocationError, RuntimeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("scripts.redaction_chat_app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()