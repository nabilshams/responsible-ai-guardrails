from io import BytesIO

from PIL import Image

from shared.guardrails.images import ImageRedactor
from shared.guardrails.models import DetectedEntity, ExtractedDocument, TextRegion


def test_burns_black_box_into_sensitive_region() -> None:
    source = Image.new("RGB", (100, 50), "white")
    buffer = BytesIO()
    source.save(buffer, format="PNG")
    document = ExtractedDocument(
        text="secret",
        regions=(TextRegion(0, 6, (10, 10, 60, 10, 60, 30, 10, 30)),),
        page_width=100,
        page_height=50,
    )
    entity = DetectedEntity("Custom", 0, 6, 1.0, "test", "secret")

    output = ImageRedactor().redact(buffer.getvalue(), document, [entity])

    with Image.open(BytesIO(output)) as redacted:
        assert redacted.getpixel((20, 20)) == (0, 0, 0)
        assert redacted.getpixel((90, 40)) == (255, 255, 255)
