"""Pixel-level image redaction based on OCR geometry."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, UnidentifiedImageError

from .models import DetectedEntity, ExtractedDocument


class ImageRedactor:
    """Burn opaque rectangles into pixels intersecting sensitive text spans."""

    def redact(
        self,
        image_bytes: bytes,
        document: ExtractedDocument,
        entities: list[DetectedEntity],
    ) -> bytes:
        try:
            with Image.open(BytesIO(image_bytes)) as source:
                source.verify()
            with Image.open(BytesIO(image_bytes)) as source:
                image = source.convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Input is not a supported image") from exc

        draw = ImageDraw.Draw(image)
        scale_x = image.width / document.page_width if document.page_width else 1.0
        scale_y = image.height / document.page_height if document.page_height else 1.0

        for region in document.regions:
            if region.page_number != 1:
                continue
            intersects = any(
                entity.offset < region.end and region.offset < entity.end
                for entity in entities
            )
            if not intersects or len(region.polygon) < 4:
                continue
            xs = region.polygon[0::2]
            ys = region.polygon[1::2]
            box = (
                max(0, int(min(xs) * scale_x) - 2),
                max(0, int(min(ys) * scale_y) - 2),
                min(image.width, int(max(xs) * scale_x) + 2),
                min(image.height, int(max(ys) * scale_y) + 2),
            )
            draw.rectangle(box, fill="black")

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
