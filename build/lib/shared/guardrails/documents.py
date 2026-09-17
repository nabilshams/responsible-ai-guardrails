"""Document text extraction adapters."""

from __future__ import annotations

from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError

from .models import ExtractedDocument, TextRegion

_TEXT_TYPES = {
    "text/plain",
    "text/csv",
    "application/json",
    "application/xml",
    "text/xml",
    "text/markdown",
}
_TEXT_SUFFIXES = {".txt", ".csv", ".json", ".xml", ".md", ".log"}


class UnsupportedDocumentError(ValueError):
    """Raised when a document cannot be processed safely."""


class DocumentExtractor:
    """Extract text locally or use Azure Document Intelligence for complex files."""

    def __init__(
        self,
        endpoint: str | None = None,
        credential: TokenCredential | None = None,
    ) -> None:
        self._client = (
            DocumentIntelligenceClient(endpoint=endpoint, credential=credential)
            if endpoint and credential
            else None
        )

    def extract(
        self,
        content: bytes,
        content_type: str,
        filename: str = "document",
    ) -> ExtractedDocument:
        suffix = Path(filename).suffix.casefold()
        if content_type in _TEXT_TYPES or suffix in _TEXT_SUFFIXES:
            try:
                return ExtractedDocument(text=content.decode("utf-8-sig"))
            except UnicodeDecodeError as exc:
                raise UnsupportedDocumentError("Text documents must use UTF-8 encoding") from exc
        if self._client is None:
            raise UnsupportedDocumentError(
                "Complex documents and images require AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"
            )

        try:
            poller = self._client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=content),
            )
            result = poller.result()
        except AzureError as exc:
            raise RuntimeError("Azure Document Intelligence request failed") from exc
        regions: list[TextRegion] = []
        page_width: float | None = None
        page_height: float | None = None
        for page in result.pages or []:
            if page.page_number == 1:
                page_width = float(page.width) if page.width is not None else None
                page_height = float(page.height) if page.height is not None else None
            for word in page.words or []:
                if not word.span or not word.polygon:
                    continue
                polygon = tuple(float(coordinate) for coordinate in word.polygon)
                regions.append(
                    TextRegion(
                        offset=int(word.span.offset),
                        length=int(word.span.length),
                        polygon=polygon,
                        page_number=int(page.page_number),
                    )
                )
        return ExtractedDocument(
            text=result.content or "",
            regions=tuple(regions),
            page_width=page_width,
            page_height=page_height,
        )
