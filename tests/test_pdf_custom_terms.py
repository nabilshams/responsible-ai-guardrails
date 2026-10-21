from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from shared.guardrails.config import Settings
from shared.guardrails.file_services import (
    DocumentAgentService,
    DocumentRedactionService,
    parse_custom_terms,
)
from shared.guardrails.models import DetectedEntity, ExtractedDocument, TextRegion
from shared.guardrails.native_document_pii import NativeDocumentRedactionResult
from shared.guardrails.pipeline import CustomTermDetector
from shared.guardrails.service import PiiRedactionService
from tests.test_pdf_redaction import build_pdf, page_text

WORD_STEP = 200.0
LINE_Y = (700.0, 650.0, 600.0)


def layout(pages: list[list[str]]) -> tuple[bytes, ExtractedDocument]:
    """Build a synthetic PDF (one Tj per word) and matching extractor output."""
    items: list[list[tuple[float, float, str]]] = []
    regions: list[TextRegion] = []
    text = ""
    for number, lines in enumerate(pages, 1):
        page_items: list[tuple[float, float, str]] = []
        for line, baseline in zip(lines, LINE_Y, strict=False):
            for index, word in enumerate(line.split()):
                x = 72 + index * WORD_STEP
                page_items.append((x, baseline, word))
                top = 792 - baseline - 12
                w = 7.0 * len(word)
                regions.append(
                    TextRegion(
                        len(text),
                        len(word),
                        (x, top, x + w, top, x + w, top + 15, x, top + 15),
                        number,
                    )
                )
                text += word + " "
            text = text.rstrip(" ") + "\n"
        items.append(page_items)
    document = ExtractedDocument(text=text, regions=tuple(regions), page_width=612, page_height=792)
    return build_pdf(items), document


class StubExtractor:
    def __init__(self, document: ExtractedDocument) -> None:
        self.document = document

    def extract(self, content: bytes, content_type: str, filename: str) -> ExtractedDocument:
        del content, content_type, filename
        return self.document


class StubDetector:
    def __init__(self, *values: str) -> None:
        self.values = values

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        del language
        found = []
        for value in self.values:
            start = 0
            while (index := text.find(value, start)) >= 0:
                found.append(DetectedEntity("Email", index, len(value), 0.99, "stub", value))
                start = index + len(value)
        return found


def service(document: ExtractedDocument, *pii_values: str) -> DocumentRedactionService:
    settings = Settings(pii_enable_azure_language=False, pii_custom_terms=[])
    pii = PiiRedactionService(settings, detector=StubDetector(*pii_values))
    return DocumentRedactionService(settings, pii, StubExtractor(document))


def redact(
    pages: list[list[str]], terms: list[str], *pii_values: str
) -> tuple[PdfReader, NativeDocumentRedactionResult]:
    pdf, document = layout(pages)
    result = service(document, *pii_values).redact_pdf(
        pdf, "application/pdf", "synthetic.pdf", custom_terms=terms
    )
    return PdfReader(io.BytesIO(result.content)), result


def all_text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() for page in reader.pages)


def test_single_word_repeated_and_case_variations_are_removed() -> None:
    reader, result = redact(
        [["Report for Falcon today", "falcon and FALCON again keep"]],
        ["Falcon"],
    )
    text = all_text(reader)
    assert "alcon" not in text.casefold()
    assert "Report" in text and "today" in text and "keep" in text
    assert result.content_type == "application/pdf"


def test_multi_word_phrase_across_words_and_lines() -> None:
    reader, _ = redact(
        [["Project Falcon launch", "Project", "Falcon notes"]],
        ["project falcon"],
    )
    text = all_text(reader)
    assert "Project" not in text and "Falcon" not in text
    assert "launch" in text and "notes" in text


def test_phrase_boundaries_do_not_match_inside_other_words() -> None:
    pdf, document = layout([["Falconer Falcons Falcon"]])
    del pdf
    entities = CustomTermDetector(["Falcon"]).detect(document.text)
    assert [document.text[e.offset : e.end] for e in entities] == ["Falcon"]
    assert entities[0].offset == document.text.rindex("Falcon")


def test_multi_page_terms_and_other_pii_overlap_and_mix() -> None:
    reader, _ = redact(
        [
            ["Alice Falcon synthetic.user@example.test visible"],
            ["Second page Falcon Contoso keep"],
        ],
        ["Falcon", "synthetic.user@example.test", "Contoso"],
        "synthetic.user@example.test",
        "Alice Falcon",
    )
    assert "Falcon" not in page_text_of(reader, 0) + page_text_of(reader, 1)
    assert "example.test" not in page_text_of(reader, 0)
    assert "visible" in page_text_of(reader, 0)
    assert "Contoso" not in page_text_of(reader, 1)
    assert "Second" in page_text_of(reader, 1) and "keep" in page_text_of(reader, 1)


def page_text_of(reader: PdfReader, index: int) -> str:
    return reader.pages[index].extract_text()


def test_no_custom_terms_leaves_other_text_readable() -> None:
    reader, _ = redact([["Nothing sensitive here"]], [])
    assert "Nothing sensitive here" in all_text(reader)


def test_agent_routes_pdf_with_terms_to_geometry_path_and_without_to_native() -> None:
    pdf, document = layout([["Secret Falcon plan"]])
    sentinel = NativeDocumentRedactionResult(b"native", "application/pdf", "a.pdf", "c")

    class Native:
        def redact(self, *args: object, **kwargs: object) -> NativeDocumentRedactionResult:
            return sentinel

    agent = DocumentAgentService(
        Settings(pii_enable_azure_language=False, pii_custom_terms=[]),
        native_redactor=Native(),  # type: ignore[arg-type]
        text_service=service(document),
    )
    assert agent.redact(pdf, "application/pdf", "a.pdf") is sentinel
    result = agent.redact(pdf, "application/pdf", "a.pdf", custom_terms=["Falcon"])
    assert isinstance(result, NativeDocumentRedactionResult)
    assert "Falcon" not in page_text(result.content, 0)
    assert "plan" in page_text(result.content, 0)
    with pytest.raises(ValueError, match="PDF and text"):
        agent.redact(b"x", "application/octet-stream", "a.docx", custom_terms=["Falcon"])


def test_text_documents_support_request_custom_terms() -> None:
    document = ExtractedDocument(text="Project Falcon is here")
    agent = DocumentAgentService(
        Settings(pii_enable_azure_language=False, pii_custom_terms=[]),
        native_redactor=object(),  # type: ignore[arg-type]
        text_service=service(document),
    )
    result = agent.redact(b"x", "text/plain", "a.txt", custom_terms=["Project Falcon"])
    assert "Falcon" not in result.redacted_text  # type: ignore[union-attr]


def test_parse_custom_terms_validation() -> None:
    assert parse_custom_terms(None) == ()
    assert parse_custom_terms(["a b", " "]) == ("a b",)
    for bad in ("Falcon", [1], ["x" * 300], ["a"] * 101):
        with pytest.raises(ValueError):
            parse_custom_terms(bad)
