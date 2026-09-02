"""Azure AI Language document-based PII redaction adapter."""

from __future__ import annotations

import io
import re
import time
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .config import Settings

_NATIVE_CONTENT_TYPES = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
_DOCX_REQUIRED_MEMBERS = frozenset({"[Content_Types].xml", "word/document.xml"})
_SAFE_ERROR_TARGET = re.compile(r"^[A-Za-z][A-Za-z0-9_.\[\]-]*$")


def validate_native_document(content: bytes, suffix: str) -> None:
    """Reject malformed native output without exposing its contents."""
    normalized_suffix = suffix.casefold()
    if not content:
        raise RuntimeError("Azure AI Language returned an empty document artifact")
    if normalized_suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if not reader.pages:
                raise RuntimeError("Azure AI Language returned an invalid PDF artifact")
        except (PdfReadError, ValueError, TypeError, OSError) as exc:
            raise RuntimeError(
                "Azure AI Language returned an invalid PDF artifact"
            ) from exc
        return
    if normalized_suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as package:
                if not _DOCX_REQUIRED_MEMBERS.issubset(package.namelist()):
                    raise RuntimeError(
                        "Azure AI Language returned an invalid DOCX artifact"
                    )
                if package.testzip() is not None:
                    raise RuntimeError(
                        "Azure AI Language returned an invalid DOCX artifact"
                    )
        except (zipfile.BadZipFile, OSError) as exc:
            raise RuntimeError(
                "Azure AI Language returned an invalid DOCX artifact"
            ) from exc
        return
    if normalized_suffix == ".txt":
        try:
            content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                "Azure AI Language returned an invalid TXT artifact"
            ) from exc
        return
    raise ValueError("Native document validation supports only TXT, PDF, and DOCX files")


@dataclass(frozen=True, slots=True)
class NativeDocumentRedactionResult:
    """A layout-preserving redacted native document held only in memory."""

    content: bytes
    content_type: str
    filename: str
    correlation_id: str


class HttpClient(Protocol):
    """Subset of the synchronous HTTP client used by the adapter."""

    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...

    def get(self, url: str, **kwargs: Any) -> httpx.Response: ...


class NativeDocumentPiiRedactor:
    """Submit native documents to Azure AI Language and retrieve redacted files."""

    def __init__(
        self,
        settings: Settings,
        credential: TokenCredential,
        *,
        blob_service: BlobServiceClient | None = None,
        http_client: HttpClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._credential = credential
        self._blob_service = blob_service
        self._http = http_client or httpx.Client(
            timeout=settings.document_pii_request_timeout_seconds
        )
        self._sleep = sleep

    def redact(
        self,
        content: bytes,
        content_type: str,
        filename: str,
        *,
        language: str,
        correlation_id: str | None = None,
    ) -> NativeDocumentRedactionResult:
        """Redact one TXT, PDF, or DOCX while preserving its native format."""
        suffix = Path(filename).suffix.casefold()
        expected_content_type = _NATIVE_CONTENT_TYPES.get(suffix)
        if expected_content_type is None:
            raise ValueError("Document-based PII supports only TXT, PDF, and DOCX files")
        if len(content) > self.settings.pii_max_upload_bytes:
            raise ValueError("Document exceeds the configured upload limit")
        if not content:
            raise ValueError("Document content cannot be empty")
        if content_type != expected_content_type:
            raise ValueError("Document content type does not match its filename")

        language_endpoint = self.settings.azure_ai_language_endpoint
        storage_endpoint = self.settings.azure_document_pii_storage_endpoint
        if not language_endpoint or not storage_endpoint:
            raise RuntimeError("Document-based PII is not configured")

        blob_service = self._blob_service or BlobServiceClient(
            account_url=storage_endpoint,
            credential=self._credential,
        )
        source_container = blob_service.get_container_client(
            self.settings.azure_document_pii_source_container
        )
        target_container = blob_service.get_container_client(
            self.settings.azure_document_pii_target_container
        )
        operation_id = uuid.uuid4().hex
        source_name = f"{operation_id}/source{suffix}"
        source_blob = source_container.get_blob_client(source_name)
        request_id = correlation_id or str(uuid.uuid4())
        target_names: list[str] = []

        try:
            source_blob.upload_blob(content, overwrite=False)
            operation_location = self._submit_job(
                language_endpoint,
                source_blob.url,
                target_container.url,
                language,
                request_id,
            )
            job = self._wait_for_completion(operation_location)
            target_names = self._target_artifact_names(job, target_container.url)
            redacted = self._download_redacted_document(target_container, target_names, suffix)
            return NativeDocumentRedactionResult(
                content=redacted,
                content_type=expected_content_type,
                filename=Path(filename).name,
                correlation_id=request_id,
            )
        except (AzureError, httpx.HTTPError) as exc:
            raise RuntimeError("Azure AI Language document redaction failed") from exc
        finally:
            self._delete_if_present(source_blob)
            self._delete_targets(target_container, target_names)

    def _authorization_headers(self) -> dict[str, str]:
        token = self._credential.get_token(_COGNITIVE_SERVICES_SCOPE)
        return {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
        }

    def _submit_job(
        self,
        endpoint: str,
        source_url: str,
        target_url: str,
        language: str,
        request_id: str,
    ) -> str:
        url = (
            f"{endpoint.rstrip('/')}/language/analyze-documents/jobs"
            f"?api-version={self.settings.azure_document_pii_api_version}"
        )
        payload = {
            "displayName": f"pii-redaction-{request_id}",
            "analysisInput": {
                "documents": [
                    {
                        "id": "document-1",
                        "language": language,
                        "source": {"kind": "AzureBlob", "location": source_url},
                        "target": {"kind": "AzureContainer", "location": target_url},
                    }
                ]
            },
            "tasks": [
                {
                    "kind": "PiiEntityRecognition",
                    "taskName": "redact-document-pii",
                    "parameters": {},
                }
            ],
        }
        response = self._http.post(url, headers=self._authorization_headers(), json=payload)
        if response.status_code != httpx.codes.ACCEPTED:
            service_code = self.safe_service_error_diagnostic(response)
            raise RuntimeError(
                "Azure AI Language rejected the document job "
                f"with HTTP {response.status_code} ({service_code})"
            )
        operation_location = str(response.headers.get("operation-location", ""))
        self.validate_operation_location(operation_location, endpoint)
        return operation_location

    @staticmethod
    def safe_service_error_diagnostic(response: httpx.Response) -> str:
        """Extract only service codes and a property-path target from an error."""
        code = response.headers.get("x-ms-error-code", "").strip()
        target = ""
        if not code:
            try:
                error = response.json().get("error", {})
                codes: list[str] = []
                current = error
                while isinstance(current, dict):
                    current_code = str(current.get("code", "")).strip()
                    if current_code:
                        codes.append(current_code)
                    current_target = str(current.get("target", "")).strip()
                    if current_target and _SAFE_ERROR_TARGET.fullmatch(current_target):
                        target = current_target
                    current = current.get("innererror")
                code = "/".join(codes)
            except (AttributeError, ValueError):
                code = ""
        diagnostic = code or "UnknownServiceError"
        return f"{diagnostic}; target={target}" if target else diagnostic

    safe_service_error_code = safe_service_error_diagnostic

    def _wait_for_completion(self, operation_location: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.document_pii_job_timeout_seconds
        while time.monotonic() < deadline:
            response = self._http.get(
                operation_location,
                headers=self._authorization_headers(),
            )
            if response.status_code != httpx.codes.OK:
                raise RuntimeError(
                    f"Azure AI Language job polling failed with HTTP {response.status_code}"
                )
            raw_payload = response.json()
            if not isinstance(raw_payload, dict):
                raise RuntimeError("Azure AI Language returned an invalid job response")
            payload: dict[str, Any] = dict(raw_payload)
            status = str(payload.get("status", "")).casefold()
            if status == "succeeded":
                return payload
            if status in {"failed", "cancelled", "canceled"}:
                raise RuntimeError("Azure AI Language document job did not succeed")
            if status not in {"running", "notstarted", "not_started"}:
                raise RuntimeError("Azure AI Language returned an unknown document job status")
            self._sleep(self.settings.document_pii_poll_interval_seconds)
        raise RuntimeError("Azure AI Language document job timed out")

    @staticmethod
    def validate_operation_location(operation_location: str, endpoint: str) -> None:
        operation = urlparse(operation_location)
        service = urlparse(endpoint)
        if (
            operation.scheme != "https"
            or not operation.hostname
            or operation.hostname.casefold() != (service.hostname or "").casefold()
        ):
            raise RuntimeError("Azure AI Language returned an invalid operation location")

    @staticmethod
    def _target_artifact_names(payload: dict[str, Any], container_url: str) -> list[str]:
        container = urlparse(container_url)
        container_path = container.path.rstrip("/") + "/"
        names: list[str] = []
        for task in payload.get("tasks", {}).get("items", []):
            for document in task.get("results", {}).get("documents", []):
                for target in document.get("targets", []):
                    location = urlparse(str(target.get("location", "")))
                    if (
                        target.get("kind") == "AzureBlob"
                        and
                        location.scheme == "https"
                        and location.hostname == container.hostname
                        and location.path.startswith(container_path)
                    ):
                        names.append(location.path[len(container_path) :])
        if not names:
            raise RuntimeError("Azure AI Language returned no document artifacts")
        return names

    @staticmethod
    def _download_redacted_document(
        target_container: Any,
        target_names: list[str],
        suffix: str,
    ) -> bytes:
        names = [name for name in target_names if name.casefold().endswith(suffix)]
        if len(names) != 1:
            raise RuntimeError("Azure AI Language returned an unexpected document artifact set")
        content = bytes(target_container.download_blob(names[0]).readall())
        validate_native_document(content, suffix)
        return content

    @staticmethod
    def _delete_if_present(blob: Any) -> None:
        try:
            blob.delete_blob(delete_snapshots="include")
        except AzureError:
            pass

    @staticmethod
    def _delete_targets(container: Any, names: list[str]) -> None:
        try:
            if names:
                container.delete_blobs(*names)
        except AzureError:
            pass
