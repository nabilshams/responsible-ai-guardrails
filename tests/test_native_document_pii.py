from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import HttpResponseError
from pypdf import PdfWriter

from shared.guardrails.config import Settings
from shared.guardrails.native_document_pii import (
    NativeDocumentPiiRedactor,
    validate_native_document,
)


class StubCredential:
    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        del scopes, kwargs
        return AccessToken("synthetic-token", 4_102_444_800)


@dataclass
class StubBlobItem:
    name: str


class StubDownload:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def readall(self) -> bytes:
        return self._content


class StubBlob:
    def __init__(self, url: str) -> None:
        self.url = url
        self.uploaded: bytes | None = None
        self.deleted = False

    def upload_blob(self, content: bytes, *, overwrite: bool) -> None:
        assert not overwrite
        self.uploaded = content

    def delete_blob(self, **kwargs: Any) -> None:
        del kwargs
        self.deleted = True


class StubContainer:
    def __init__(self, url: str, artifact: bytes = b"") -> None:
        self.url = url
        self.artifact = artifact
        self.blob: StubBlob | None = None
        self.deleted_names: tuple[str, ...] = ()

    def get_blob_client(self, name: str) -> StubBlob:
        self.blob = StubBlob(f"{self.url}/{name}")
        return self.blob

    def list_blobs(self, *, name_starts_with: str) -> list[StubBlobItem]:
        return [StubBlobItem(f"{name_starts_with}redacted.pdf")] if self.artifact else []

    def download_blob(self, name: str) -> StubDownload:
        assert name.endswith("redacted.pdf")
        return StubDownload(self.artifact)

    def delete_blobs(self, *names: str) -> None:
        self.deleted_names = names


class StubBlobService:
    def __init__(self, redacted: bytes) -> None:
        root = "https://synthetic.blob.core.windows.net"
        self.source = StubContainer(f"{root}/pii-source")
        self.target = StubContainer(f"{root}/pii-target", redacted)

    def get_container_client(self, name: str) -> StubContainer:
        return self.source if name == "pii-source" else self.target


class StubHttpClient:
    def __init__(self) -> None:
        self.submission: dict[str, Any] | None = None

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.submission = kwargs["json"]
        return httpx.Response(
            202,
            headers={
                "operation-location": (
                    "https://synthetic.cognitiveservices.azure.com/language/"
                    "analyze-documents/jobs/synthetic?api-version=2026-05-01"
                )
            },
            request=httpx.Request("POST", url),
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        del kwargs
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "tasks": {
                    "items": [
                        {
                            "results": {
                                "documents": [
                                    {
                                        "targets": [
                                            {
                                                "kind": "AzureBlob",
                                                "location": (
                                                    "https://synthetic.blob.core.windows.net/"
                                                    "pii-target/job/redacted.result.json"
                                                )
                                            },
                                            {
                                                "kind": "AzureBlob",
                                                "location": (
                                                    "https://synthetic.blob.core.windows.net/"
                                                    "pii-target/job/redacted.pdf"
                                                )
                                            },
                                        ]
                                    }
                                ]
                            }
                        }
                    ]
                },
            },
            request=httpx.Request("GET", url),
        )


def configured_settings() -> Settings:
    return Settings(
        azure_ai_language_endpoint="https://synthetic.cognitiveservices.azure.com",
        azure_document_pii_storage_endpoint="https://synthetic.blob.core.windows.net",
    )


def valid_pdf() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def valid_docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("word/document.xml", "<document />")
    return output.getvalue()


def test_redacts_native_pdf_and_deletes_temporary_blobs() -> None:
    redacted_pdf = valid_pdf()
    storage = StubBlobService(redacted_pdf)
    http = StubHttpClient()
    redactor = NativeDocumentPiiRedactor(
        configured_settings(),
        StubCredential(),  # type: ignore[arg-type]
        blob_service=storage,  # type: ignore[arg-type]
        http_client=http,
        sleep=lambda _: None,
    )

    result = redactor.redact(
        b"%PDF-synthetic-source",
        "application/pdf",
        "synthetic.pdf",
        language="en",
        correlation_id="synthetic-correlation",
    )

    assert result.content == redacted_pdf
    assert result.filename == "synthetic.pdf"
    assert result.content_type == "application/pdf"
    assert storage.source.blob is not None
    assert storage.source.blob.deleted
    assert len(storage.target.deleted_names) == 2
    assert http.submission is not None
    parameters = http.submission["tasks"][0]["parameters"]
    assert parameters == {}


def test_rejects_malformed_native_pdf_artifact() -> None:
    storage = StubBlobService(b"not-a-pdf")
    redactor = NativeDocumentPiiRedactor(
        configured_settings(),
        StubCredential(),  # type: ignore[arg-type]
        blob_service=storage,  # type: ignore[arg-type]
        http_client=StubHttpClient(),
        sleep=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="invalid PDF artifact"):
        redactor.redact(
            valid_pdf(),
            "application/pdf",
            "synthetic.pdf",
            language="en",
        )

    assert storage.source.blob is not None
    assert storage.source.blob.deleted
    assert len(storage.target.deleted_names) == 2


class BlockedBlob(StubBlob):
    def __init__(self, url: str, error: Exception) -> None:
        super().__init__(url)
        self._error = error

    def upload_blob(self, content: bytes, *, overwrite: bool) -> None:
        del content, overwrite
        raise self._error


def blocked_storage(error: Exception) -> StubBlobService:
    storage = StubBlobService(b"")

    def get_blob_client(name: str) -> BlockedBlob:
        storage.source.blob = BlockedBlob(f"{storage.source.url}/{name}", error)
        return storage.source.blob

    storage.source.get_blob_client = get_blob_client  # type: ignore[method-assign]
    return storage


def redact_with_storage_error(error: Exception) -> RuntimeError:
    redactor = NativeDocumentPiiRedactor(
        configured_settings(),
        StubCredential(),  # type: ignore[arg-type]
        blob_service=blocked_storage(error),  # type: ignore[arg-type]
        http_client=StubHttpClient(),
        sleep=lambda _: None,
    )
    with pytest.raises(RuntimeError) as raised:
        redactor.redact(
            valid_pdf(),
            "application/pdf",
            "synthetic.pdf",
            language="en",
        )
    return raised.value


def test_storage_failure_reports_status_and_error_code_only() -> None:
    error = HttpResponseError(message="synthetic secret detail https://private.invalid/x")
    error.status_code = 403
    error.error_code = "AuthorizationFailure"  # type: ignore[attr-defined]

    failure = redact_with_storage_error(error)

    assert str(failure) == (
        "Azure AI Language document redaction failed "
        "(HttpResponseError; status=403; code=AuthorizationFailure)"
    )
    assert "secret" not in str(failure)
    assert "private.invalid" not in str(failure)


def test_transport_failure_reports_exception_class_only() -> None:
    failure = redact_with_storage_error(httpx.ConnectError("synthetic host detail"))

    assert str(failure) == "Azure AI Language document redaction failed (ConnectError)"


def test_unsafe_error_code_is_omitted() -> None:
    error = HttpResponseError(message="synthetic")
    error.status_code = 400
    error.error_code = "bad code with spaces and https://private.invalid"  # type: ignore[attr-defined]

    failure = redact_with_storage_error(error)

    assert str(failure).endswith("(HttpResponseError; status=400)")


@pytest.mark.parametrize(
    ("content", "suffix"),
    [
        (valid_pdf(), ".pdf"),
        (valid_docx(), ".docx"),
        (b"synthetic text", ".txt"),
    ],
)
def test_accepts_valid_native_document_artifacts(content: bytes, suffix: str) -> None:
    validate_native_document(content, suffix)


@pytest.mark.parametrize(
    ("content", "suffix", "message"),
    [
        (b"not-a-pdf", ".pdf", "invalid PDF artifact"),
        (b"not-a-docx", ".docx", "invalid DOCX artifact"),
        (b"\xff", ".txt", "invalid TXT artifact"),
    ],
)
def test_rejects_malformed_native_document_artifacts(
    content: bytes,
    suffix: str,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_native_document(content, suffix)


def test_ignores_target_artifacts_without_azure_blob_kind() -> None:
    payload = {
        "tasks": {
            "items": [
                {
                    "results": {
                        "documents": [
                            {
                                "targets": [
                                    {
                                        "kind": "AzureContainer",
                                        "location": (
                                            "https://synthetic.blob.core.windows.net/"
                                            "pii-target/job/redacted.pdf"
                                        ),
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }
    }

    with pytest.raises(RuntimeError, match="no document artifacts"):
        NativeDocumentPiiRedactor._target_artifact_names(
            payload,
            "https://synthetic.blob.core.windows.net/pii-target",
        )


def test_rejects_format_not_supported_by_document_based_pii() -> None:
    redactor = NativeDocumentPiiRedactor(
        configured_settings(),
        StubCredential(),  # type: ignore[arg-type]
        blob_service=StubBlobService(b"redacted"),  # type: ignore[arg-type]
        http_client=StubHttpClient(),
    )

    with pytest.raises(ValueError, match="TXT, PDF, and DOCX"):
        redactor.redact(
            b"synthetic",
            "text/csv",
            "synthetic.csv",
            language="en",
        )


def test_rejects_operation_location_on_another_host() -> None:
    with pytest.raises(RuntimeError, match="invalid operation location"):
        NativeDocumentPiiRedactor.validate_operation_location(
            "https://untrusted.example.test/jobs/1",
            "https://synthetic.cognitiveservices.azure.com",
        )


def test_extracts_only_safe_service_error_codes() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "code": "InvalidRequest",
                "message": "potentially sensitive detail",
                "innererror": {
                    "code": "InvalidParameterValue",
                    "target": "tasks[0].parameters.redactionPolicies[0].policyKind",
                    "innererror": {"code": "InvalidDocument"},
                },
            }
        },
    )

    assert (
        NativeDocumentPiiRedactor.safe_service_error_diagnostic(response)
        == (
            "InvalidRequest/InvalidParameterValue/InvalidDocument; "
            "target=tasks[0].parameters.redactionPolicies[0].policyKind"
        )
    )


def test_does_not_expose_unsafe_service_error_target() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "code": "InvalidRequest",
                "innererror": {
                    "code": "InvalidParameterValue",
                    "target": "https://sensitive.example.test/value",
                },
            }
        },
    )

    diagnostic = NativeDocumentPiiRedactor.safe_service_error_diagnostic(response)

    assert diagnostic == "InvalidRequest/InvalidParameterValue"
    assert "https://" not in diagnostic
