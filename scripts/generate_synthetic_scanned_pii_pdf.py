"""Generate a visibly synthetic PDF fixture whose PII appears only in a raster image."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_OUTPUT = Path("samples/input/synthetic-scanned-pii.pdf")
_PAGE_SIZE = (1654, 2339)
_MARGIN = 150


def create_scanned_pii_pdf(destination: Path = _OUTPUT) -> Path:
    """Create one rasterized, visibly synthetic document page as a PDF."""
    page = Image.new("L", _PAGE_SIZE, color=242)
    draw = ImageDraw.Draw(page)
    heading_font = ImageFont.load_default(size=54)
    body_font = ImageFont.load_default(size=35)
    small_font = ImageFont.load_default(size=25)

    draw.rectangle((90, 90, 1564, 2249), outline=90, width=4)
    draw.rectangle((120, 120, 1534, 300), fill=218)
    draw.text((170, 165), "SYNTHETIC SCANNED INTAKE FORM", fill=28, font=heading_font)

    lines = [
        "Training fixture only - contains no real personal data.",
        "",
        "Applicant name: Synthetic Sampleperson",
        "Email: synthetic.user@example.test",
        "Phone: 555-010-0420",
        "Address: 123 Synthetic Avenue, Example City, EX 00000",
        "",
        "Processing note: redaction evaluation document.",
    ]
    y_position = 400
    for line in lines:
        draw.text((_MARGIN, y_position), line, fill=45, font=body_font)
        y_position += 105

    draw.line((_MARGIN, 1370, 1504, 1370), fill=140, width=2)
    draw.text(
        (_MARGIN, 1425),
        "SYNTHETIC DATA - DO NOT USE FOR IDENTITY VERIFICATION",
        fill=75,
        font=small_font,
    )

    page = page.filter(ImageFilter.GaussianBlur(radius=0.35))
    destination.parent.mkdir(parents=True, exist_ok=True)
    page.convert("RGB").save(destination, format="PDF", resolution=200.0)
    return destination


if __name__ == "__main__":
    create_scanned_pii_pdf()