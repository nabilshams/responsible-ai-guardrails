"""Span-based PDF redaction that removes glyphs from page content streams.

The adapter maps page-aware detected spans (word polygons from ``DocumentExtractor``)
onto the source PDF, deletes the intersecting text-showing operands from the content
stream, and verifies the output no longer exposes any redacted value. It never draws a
covering rectangle as the only protection. Documents whose content cannot be redacted
safely (images, form XObjects, malformed files, unmapped spans) raise
``PdfRedactionError`` instead of returning an apparently successful artifact.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from .models import DetectedEntity, ExtractedDocument

Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_BOX_PADDING = 1.0
_ASCENT = 0.95
_DESCENT = 0.3
_DEFAULT_WIDTH = 600.0
_NARROW = set("ijl.,:;'!|()[]{}fIt -/")
_WIDE = set("mwMW@")


class PdfRedactionError(ValueError):
    """Raised when a PDF cannot be redacted safely."""


@dataclass(frozen=True, slots=True)
class PdfRedactionBox:
    """Rectangle on a displayed page, in extractor units with a top-left origin."""

    page_number: int
    x0: float
    y0: float
    x1: float
    y1: float


def _mul(a: Matrix, b: Matrix) -> Matrix:
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _bounds(matrix: Matrix, x0: float, y0: float, x1: float, y1: float) -> tuple[float, ...]:
    points = [
        (x * matrix[0] + y * matrix[2] + matrix[4], x * matrix[1] + y * matrix[3] + matrix[5])
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    ]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlaps(a: tuple[float, ...], rects: list[tuple[float, float, float, float]]) -> bool:
    return any(a[0] < r[2] and r[0] < a[2] and a[1] < r[3] and r[1] < a[3] for r in rects)


def _num(value: Any) -> float:
    return float(value)


def _string_bytes(value: Any) -> bytes:
    if isinstance(value, ByteStringObject):
        return bytes(value)
    original = getattr(value, "original_bytes", None)
    if original is not None:
        return bytes(original)
    return str(value).encode("latin-1", errors="replace")


class _Font:
    """Glyph-width model for a PDF font resource."""

    def __init__(self, font: Any | None) -> None:
        self.two_byte = False
        self.first_char = 0
        self.widths: list[float] = []
        self.missing = _DEFAULT_WIDTH
        self.default_width = _DEFAULT_WIDTH
        self.core: dict[str, float] = {}
        if font is None:
            return
        font = font.get_object()
        if font.get("/Subtype") == "/Type0":
            self.two_byte = True
            self.default_width = 1000.0
            descendants = font.get("/DescendantFonts")
            if descendants:
                self.default_width = float(descendants[0].get_object().get("/DW", 1000))
            return
        if "/Widths" in font:
            self.first_char = int(font.get("/FirstChar", 0))
            self.widths = [float(w) for w in font["/Widths"]]
            descriptor = font.get("/FontDescriptor")
            if descriptor is not None:
                self.missing = float(descriptor.get_object().get("/MissingWidth", 0)) or 0.0
        else:
            self.core = _core_widths(str(font.get("/BaseFont", "")))

    def codes(self, data: bytes) -> list[bytes]:
        if self.two_byte:
            return [data[i : i + 2] for i in range(0, len(data), 2)]
        return [data[i : i + 1] for i in range(len(data))]

    def width(self, code: bytes) -> float:
        if self.two_byte:
            return self.default_width
        value = code[0]
        if self.widths:
            index = value - self.first_char
            if 0 <= index < len(self.widths):
                return self.widths[index]
            return self.missing
        char = chr(value)
        if self.core:
            return self.core.get(char, self.core.get("default", _DEFAULT_WIDTH))
        if char in _NARROW:
            return 350.0
        if char in _WIDE:
            return 900.0
        if char.isupper():
            return 750.0
        return _DEFAULT_WIDTH


def _core_widths(base_font: str) -> dict[str, float]:
    name = base_font.lstrip("/").split("+")[-1].lower()
    if name.startswith("courier"):
        return {"default": 600.0}
    key = None
    if name.startswith(("helvetica", "arial")):
        key = "Helvetica"
    elif name.startswith("times"):
        key = "Times-Roman"
    if key is None:
        return {}
    try:
        from pypdf._codecs.core_font_metrics import CORE_FONT_METRICS

        widths = CORE_FONT_METRICS[key].character_widths
        return {str(k): float(v) for k, v in widths.items()}
    except (ImportError, KeyError, AttributeError):
        return {}


class _PageRedactor:
    """Interprets text operators and removes glyphs inside redaction rectangles."""

    def __init__(self, fonts: Any, rects: list[tuple[float, float, float, float]]) -> None:
        self._fonts = fonts
        self._rects = rects
        self._cache: dict[str, _Font] = {}
        self.removed = 0

    def _font(self, name: str) -> _Font:
        if name not in self._cache:
            resource = self._fonts.get(name) if self._fonts is not None else None
            self._cache[name] = _Font(resource)
        return self._cache[name]

    def process(self, operations: list[tuple[Any, bytes]]) -> list[tuple[Any, bytes]]:
        output: list[tuple[Any, bytes]] = []
        ctm = _IDENTITY
        stack: list[Matrix] = []
        tm = tlm = _IDENTITY
        font = self._font("")
        size = 0.0
        tc = tw = rise = leading = 0.0
        th = 1.0

        def show(items: list[Any]) -> list[Any]:
            nonlocal tm
            result: list[Any] = []
            for item in items:
                if isinstance(item, (int, float, NumberObject, FloatObject)):
                    shift = -_num(item) / 1000.0 * size * th
                    tm = _mul((1, 0, 0, 1, shift, 0), tm)
                    result.append(item)
                    continue
                kept = bytearray()
                for code in font.codes(_string_bytes(item)):
                    advance = font.width(code) / 1000.0 * size
                    advance += tc + (tw if code == b" " else 0.0)
                    advance *= th
                    full = _mul(tm, ctm)
                    box = _bounds(
                        full, 0, -_DESCENT * size + rise, advance, _ASCENT * size + rise
                    )
                    if _overlaps(box, self._rects):
                        self.removed += 1
                        if kept:
                            result.append(ByteStringObject(bytes(kept)))
                            kept = bytearray()
                        if size:
                            result.append(FloatObject(-advance / size * 1000.0 / th))
                    else:
                        kept.extend(code)
                    tm = _mul((1, 0, 0, 1, advance, 0), tm)
                if kept:
                    result.append(ByteStringObject(bytes(kept)))
            return result

        for operands, operator in operations:
            if operator == b"q":
                stack.append(ctm)
            elif operator == b"Q":
                ctm = stack.pop() if stack else ctm
            elif operator == b"cm":
                ctm = _mul(tuple(_num(v) for v in operands), ctm)  # type: ignore[arg-type]
            elif operator == b"BT":
                tm = tlm = _IDENTITY
            elif operator == b"Tf":
                font = self._font(str(operands[0]))
                size = _num(operands[1])
            elif operator == b"Tc":
                tc = _num(operands[0])
            elif operator == b"Tw":
                tw = _num(operands[0])
            elif operator == b"Tz":
                th = _num(operands[0]) / 100.0
            elif operator == b"TL":
                leading = _num(operands[0])
            elif operator == b"Ts":
                rise = _num(operands[0])
            elif operator in (b"Td", b"TD"):
                tx, ty = _num(operands[0]), _num(operands[1])
                if operator == b"TD":
                    leading = -ty
                tlm = _mul((1, 0, 0, 1, tx, ty), tlm)
                tm = tlm
            elif operator == b"Tm":
                tm = tlm = tuple(_num(v) for v in operands)  # type: ignore[assignment]
            elif operator == b"T*":
                tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
                tm = tlm
            elif operator in (b"Tj", b"TJ", b"'", b'"'):
                if operator in (b"'", b'"'):
                    if operator == b'"':
                        tw, tc = _num(operands[0]), _num(operands[1])
                        output.append(([operands[0]], b"Tw"))
                        output.append(([operands[1]], b"Tc"))
                    tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
                    tm = tlm
                    output.append(([], b"T*"))
                    items = [operands[-1]]
                else:
                    items = list(operands[0]) if operator == b"TJ" else [operands[0]]
                output.append(([ArrayObject(show(items))], b"TJ"))
                continue
            output.append((operands, operator))
        return output


class PdfSpanRedactor:
    """Redact page-aware detected spans from a PDF and return a validated PDF."""

    def redact(
        self,
        pdf_bytes: bytes,
        document: ExtractedDocument,
        entities: list[DetectedEntity],
    ) -> bytes:
        """Map entities to word regions of ``document`` and redact the PDF."""

        if not document.page_width or not document.page_height:
            raise PdfRedactionError("Page dimensions are required to map spans onto the PDF")
        boxes: list[PdfRedactionBox] = []
        values: list[str] = []
        for entity in entities:
            matched = [
                region
                for region in document.regions
                if entity.offset < region.end and region.offset < entity.end
                and len(region.polygon) >= 4
            ]
            if not matched:
                raise PdfRedactionError("A detected span could not be mapped to page geometry")
            for region in matched:
                xs, ys = region.polygon[0::2], region.polygon[1::2]
                boxes.append(
                    PdfRedactionBox(region.page_number, min(xs), min(ys), max(xs), max(ys))
                )
            values.append(entity.value)
        return self.redact_boxes(
            pdf_bytes,
            boxes,
            page_width=document.page_width,
            page_height=document.page_height,
            values=values,
        )

    def redact_boxes(
        self,
        pdf_bytes: bytes,
        boxes: list[PdfRedactionBox],
        *,
        page_width: float,
        page_height: float,
        values: list[str] | None = None,
    ) -> bytes:
        """Redact explicit page boxes; ``values`` are verified absent from the output."""

        if page_width <= 0 or page_height <= 0:
            raise PdfRedactionError("Page dimensions must be positive")
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            if reader.is_encrypted:
                raise PdfRedactionError("Encrypted PDFs are not supported")
            page_count = len(reader.pages)
            by_page: dict[int, list[PdfRedactionBox]] = defaultdict(list)
            for box in boxes:
                if not 1 <= box.page_number <= page_count:
                    raise PdfRedactionError("A redaction box references a missing page")
                by_page[box.page_number].append(box)

            writer = PdfWriter()
            writer.append(reader)
            for number, page_boxes in by_page.items():
                page = writer.pages[number - 1]
                self._redact_page(writer, page, page_boxes, page_width, page_height)
            output = BytesIO()
            writer.write(output)
        except PdfRedactionError:
            raise
        except (PyPdfError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise PdfRedactionError("PDF could not be parsed or redacted safely") from exc

        result = output.getvalue()
        self._verify(result, page_count, values or [])
        return result

    def _redact_page(
        self,
        writer: PdfWriter,
        page: Any,
        boxes: list[PdfRedactionBox],
        page_width: float,
        page_height: float,
    ) -> None:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else DictionaryObject()
        xobjects = resources.get("/XObject")
        if xobjects is not None and len(xobjects.get_object()) > 0:
            raise PdfRedactionError(
                "Pages with image or form XObjects cannot be redacted safely"
            )
        rects = [self._to_user_space(page, b, page_width, page_height) for b in boxes]
        fonts = resources.get("/Font")
        fonts = fonts.get_object() if fonts is not None else None
        contents = page.get_contents()
        if contents is None:
            raise PdfRedactionError("Page has no content stream to redact")
        stream = ContentStream(contents, writer)
        if any(op == b"BI" for _, op in stream.operations):
            raise PdfRedactionError("Inline images cannot be redacted safely")
        redactor = _PageRedactor(fonts, rects)
        stream.operations = redactor.process(stream.operations)
        page.replace_contents(stream)
        if "/Annots" in page:
            del page[NameObject("/Annots")]

    @staticmethod
    def _to_user_space(
        page: Any, box: PdfRedactionBox, page_width: float, page_height: float
    ) -> tuple[float, float, float, float]:
        media = page.cropbox
        left, bottom = float(media.left), float(media.bottom)
        width, height = float(media.width), float(media.height)
        rotation = int(page.get("/Rotate", 0) or 0) % 360
        corners = []
        for x, y in ((box.x0, box.y0), (box.x1, box.y1)):
            du, dv = x / page_width, y / page_height
            if rotation == 0:
                p, q = du, 1 - dv
            elif rotation == 90:
                p, q = dv, du
            elif rotation == 180:
                p, q = 1 - du, dv
            elif rotation == 270:
                p, q = 1 - dv, 1 - du
            else:
                raise PdfRedactionError("Unsupported page rotation")
            corners.append((left + p * width, bottom + q * height))
        (ax, ay), (bx, by) = corners
        return (
            min(ax, bx) - _BOX_PADDING,
            min(ay, by) - _BOX_PADDING,
            max(ax, bx) + _BOX_PADDING,
            max(ay, by) + _BOX_PADDING,
        )

    @staticmethod
    def _verify(pdf_bytes: bytes, page_count: int, values: list[str]) -> None:
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            if len(reader.pages) != page_count:
                raise PdfRedactionError("Redacted PDF page count changed")
            text = "".join(page.extract_text() or "" for page in reader.pages)
        except PyPdfError as exc:
            raise PdfRedactionError("Redacted PDF failed validation") from exc
        squashed = re.sub(r"\s+", "", text)
        for value in values:
            needle = re.sub(r"\s+", "", value)
            if needle and needle in squashed:
                raise PdfRedactionError("Redacted PDF still exposes a sensitive value")
