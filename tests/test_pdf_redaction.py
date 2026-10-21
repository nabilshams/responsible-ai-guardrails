from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from shared.guardrails.models import DetectedEntity, ExtractedDocument, TextRegion
from shared.guardrails.pdf_redaction import (
    PdfRedactionBox,
    PdfRedactionError,
    PdfSpanRedactor,
)


def build_pdf(
    pages: list[list[tuple[float, float, str]]],
    *,
    rotate: int = 0,
    extra_resources: str = "",
) -> bytes:
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font_id = 3 + 2 * len(pages)
    for i, items in enumerate(pages):
        body = "BT /F1 12 Tf\n"
        for x, y, text in items:
            body += f"1 0 0 1 {x} {y} Tm ({text}) Tj\n"
        body += "ET"
        rotation = f"/Rotate {rotate} " if rotate else ""
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] {rotation}"
                f"/Contents {4 + 2 * i} 0 R "
                f"/Resources << /Font << /F1 {font_id} 0 R >> {extra_resources} >> >>"
            ).encode()
        )
        objects.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream".encode())
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    ).encode()
    return bytes(out)


def page_text(pdf: bytes, index: int) -> str:
    return PdfReader(BytesIO(pdf)).pages[index].extract_text()


def box(page: int, x0: float, y0: float, x1: float, y1: float) -> PdfRedactionBox:
    return PdfRedactionBox(page, x0, y0, x1, y1)


# Page units == PDF points; top-left origin, so y_top = 792 - baseline - 12.
def test_multi_page_multiple_redactions_remove_only_targets() -> None:
    pdf = build_pdf(
        [
            [(72, 700, "Alpha SECRETONE beta"), (72, 600, "Keep this line")],
            [(72, 700, "Page two SECRETTWO here"), (72, 500, "SECRETTHREE tail")],
        ]
    )
    boxes = [
        box(1, 72, 792 - 700 - 12, 300, 792 - 700 + 3),
        box(2, 72, 792 - 700 - 12, 300, 792 - 700 + 3),
        box(2, 72, 792 - 500 - 12, 300, 792 - 500 + 3),
    ]
    out = PdfSpanRedactor().redact_boxes(
        pdf, boxes, page_width=612, page_height=792, values=[]
    )
    first, second = page_text(out, 0), page_text(out, 1)
    assert "SECRET" not in first + second
    assert "Keep this line" in first
    assert b"SECRET" not in out


def test_partial_line_redaction_preserves_neighbours() -> None:
    pdf = build_pdf([[(72, 700, "Name: Jane Doe end")]])
    # Cover roughly "Jane Doe" (x 72+~36 .. 72+~85)
    out = PdfSpanRedactor().redact_boxes(
        pdf,
        [box(1, 111, 792 - 700 - 12, 154, 792 - 700 + 3)],
        page_width=612,
        page_height=792,
        values=["Jane"],
    )
    text = page_text(out, 0)
    assert "Jane" not in text
    assert text.startswith("Name:")
    assert "end" in text


@pytest.mark.parametrize("rotate", [90, 180, 270])
def test_rotated_pages_map_coordinates(rotate: int) -> None:
    pdf = build_pdf([[(72, 700, "ROTATED SECRET"), (72, 100, "other text")]], rotate=rotate)
    # Compute displayed-space box for the unrotated rectangle around the first line.
    x0, y0, x1, y1 = 72.0, 700 - 3.0, 72 + 100.0, 700 + 12.0
    w, h = 612.0, 792.0

    def disp(x: float, y: float) -> tuple[float, float]:
        p, q = x / w, y / h
        if rotate == 90:
            return q, p
        if rotate == 180:
            return 1 - p, q
        return 1 - q, 1 - p

    (ax, ay), (bx, by) = disp(x0, y0), disp(x1, y1)
    dw, dh = (h, w) if rotate in (90, 270) else (w, h)
    b = box(1, min(ax, bx) * dw, min(ay, by) * dh, max(ax, bx) * dw, max(ay, by) * dh)
    out = PdfSpanRedactor().redact_boxes(pdf, [b], page_width=dw, page_height=dh)
    text = page_text(out, 0)
    assert "SECRET" not in text
    assert "other text" in text


def test_redact_from_entities_and_extracted_document() -> None:
    pdf = build_pdf([[(72, 700, "Call 555-0100 now")]])
    text = "Call 555-0100 now"
    top, bottom = 792 - 700 - 12, 792 - 700 + 3
    region = TextRegion(
        offset=5,
        length=8,
        polygon=(108, top, 150, top, 150, bottom, 108, bottom),
        page_number=1,
    )
    document = ExtractedDocument(
        text=text, regions=(region,), page_width=612, page_height=792
    )
    entity = DetectedEntity("Phone", 5, 8, 1.0, "test", value="555-0100")
    out = PdfSpanRedactor().redact(pdf, document, [entity])
    assert "555-0100" not in page_text(out, 0)


def test_unmapped_entity_fails() -> None:
    pdf = build_pdf([[(72, 700, "hello")]])
    document = ExtractedDocument(text="hello", regions=(), page_width=612, page_height=792)
    entity = DetectedEntity("X", 0, 5, 1.0, "test", value="hello")
    with pytest.raises(PdfRedactionError):
        PdfSpanRedactor().redact(pdf, document, [entity])


def test_malformed_pdf_missing_page_and_images_fail() -> None:
    redactor = PdfSpanRedactor()
    with pytest.raises(PdfRedactionError):
        redactor.redact_boxes(b"not a pdf", [box(1, 0, 0, 1, 1)], page_width=1, page_height=1)
    pdf = build_pdf([[(72, 700, "hello")]])
    with pytest.raises(PdfRedactionError):
        redactor.redact_boxes(pdf, [box(2, 0, 0, 1, 1)], page_width=612, page_height=792)
    with_image = build_pdf([[(72, 700, "hello")]], extra_resources="/XObject << /Im1 1 0 R >>")
    with pytest.raises(PdfRedactionError):
        redactor.redact_boxes(
            with_image, [box(1, 0, 0, 10, 10)], page_width=612, page_height=792
        )


def test_verification_fails_when_value_survives() -> None:
    pdf = build_pdf([[(72, 700, "hello SECRET")]])
    with pytest.raises(PdfRedactionError):
        PdfSpanRedactor().redact_boxes(
            pdf, [box(1, 0, 0, 5, 5)], page_width=612, page_height=792, values=["SECRET"]
        )
