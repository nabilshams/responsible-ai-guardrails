"""Generate visibly synthetic PNG and JPEG fixtures with OCR-readable PII."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_OUTPUT_ROOT = Path("samples/input")
_SIZE = (1600, 760)


def create_synthetic_image_samples(
    destination: Path = _OUTPUT_ROOT,
) -> tuple[Path, Path]:
    """Create non-sensitive PNG and JPEG image-redaction fixtures."""
    image = Image.new("RGB", _SIZE, "white")
    draw = ImageDraw.Draw(image)
    heading = ImageFont.load_default(size=62)
    body = ImageFont.load_default(size=46)
    notice = ImageFont.load_default(size=32)

    draw.rectangle((35, 35, 1565, 725), outline=(35, 85, 135), width=5)
    draw.rectangle((70, 70, 1530, 190), fill=(222, 237, 250))
    draw.text((105, 95), "SYNTHETIC TEST IMAGE", fill=(20, 55, 90), font=heading)

    lines = (
        "Name: Synthetic Image Person",
        "Email: synthetic.image@example.test",
        "Phone: +1-202-555-0199",
        "Address: 246 Example Boulevard, Test City, ZZ 00000",
    )
    y_position = 255
    for line in lines:
        draw.text((105, y_position), line, fill=(25, 25, 25), font=body)
        y_position += 82

    draw.text(
        (105, 625),
        "NOT A REAL PERSON - OCR AND PII REDACTION TESTING ONLY",
        fill=(135, 35, 35),
        font=notice,
    )

    destination.mkdir(parents=True, exist_ok=True)
    png_path = destination / "synthetic-pii-image.png"
    jpeg_path = destination / "synthetic-pii-image.jpg"
    image.save(png_path, format="PNG")
    image.save(jpeg_path, format="JPEG", quality=92, optimize=True)
    return png_path, jpeg_path


if __name__ == "__main__":
    create_synthetic_image_samples()
