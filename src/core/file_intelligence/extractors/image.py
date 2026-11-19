"""Header-only image metadata with an explicit EXIF allowlist (no GPS fields)."""

import io
import re
import struct
import xml.etree.ElementTree as ET

from src.core.file_intelligence.extractors._binary import (
    BinaryExtractor, HeaderLimit, clean, dimensions, keyword,
)


_EXIF_FIELDS = {271: "Make", 272: "Model", 305: "Software", 306: "DateTime",
                36867: "DateTimeOriginal", 42036: "LensModel"}


def _tiff(stream, result, size):
    """Inspect IFD0 and the EXIF IFD only; the GPS pointer is never followed."""
    stream.seek(0)
    header = stream.read(8)
    if len(header) != 8 or header[:2] not in (b"II", b"MM"):
        return
    endian = "<" if header[:2] == b"II" else ">"
    if struct.unpack(endian + "H", header[2:4])[0] != 42:
        return
    pending = [struct.unpack(endian + "I", header[4:8])[0]]
    seen = set()
    for _ in range(2):
        if not pending:
            break
        offset = pending.pop()
        if offset in seen or offset < 8 or offset + 2 > size:
            break
        seen.add(offset)
        stream.seek(offset)
        count_data = stream.read(2)
        if len(count_data) != 2:
            break
        count = min(struct.unpack(endian + "H", count_data)[0], 128)
        width = height = None
        for index in range(count):
            position = offset + 2 + 12 * index
            if position + 12 > size:
                break
            stream.seek(position)
            entry = stream.read(12)
            if len(entry) != 12:
                break
            tag, kind, length = struct.unpack(endian + "HHI", entry[:8])
            if tag == 34665 and kind == 4 and length == 1:
                pending.append(struct.unpack(endian + "I", entry[8:12])[0])
            elif tag in (256, 257) and kind in (3, 4) and length == 1:
                value = struct.unpack(endian + ("H" if kind == 3 else "I"), entry[8:10] if kind == 3 else entry[8:12])[0]
                if tag == 256:
                    width = value
                else:
                    height = value
            elif tag in _EXIF_FIELDS and kind == 2 and 0 < length <= 1024:
                if length <= 4:
                    raw = entry[8:8 + length]
                else:
                    pointer = struct.unpack(endian + "I", entry[8:12])[0]
                    if pointer + length > size:
                        continue
                    stream.seek(pointer)
                    raw = stream.read(length)
                value = clean(raw.rstrip(b"\x00"))
                if value:
                    result.exif_tags[_EXIF_FIELDS[tag]] = value
        if width and height:
            dimensions(result, width, height)


def _exif_bytes(raw, result):
    if raw.startswith(b"Exif\x00\x00"):
        raw = raw[6:]
    # EXIF can describe an older image size or thumbnail. The container's
    # dimensions remain authoritative; standalone TIFF uses _tiff directly.
    original_dimensions = result.dimensions
    try:
        _tiff(io.BytesIO(raw), result, len(raw))
    finally:
        result.dimensions = original_dimensions


def _jpeg(reader, result):
    reader.seek(2)
    for _ in range(256):
        marker = reader.read(2)
        if len(marker) < 2 or marker[0] != 255:
            break
        while marker[1] == 255:
            marker = b"\xff" + reader.read(1)
            if len(marker) < 2:
                return
        kind = marker[1]
        if kind in (0xD9, 0xDA):
            break
        if kind == 0xD8 or 0xD0 <= kind <= 0xD7:
            continue
        raw = reader.read(2)
        if len(raw) != 2:
            break
        length = int.from_bytes(raw, "big") - 2
        start = reader.tell()
        if length < 0 or start + length > reader.size:
            break
        if kind == 0xE1:
            _exif_bytes(reader.read(length), result)
        elif kind in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and length >= 5:
            raw = reader.read(5)
            dimensions(result, int.from_bytes(raw[3:5], "big"), int.from_bytes(raw[1:3], "big"))
        reader.seek(start + length)


def _png(reader, result):
    reader.seek(8)
    for _ in range(128):
        header = reader.read(8)
        if len(header) != 8:
            break
        size, name = struct.unpack(">I4s", header)
        start = reader.tell()
        if start + size + 4 > reader.size:
            break
        if name == b"IHDR" and size == 13:
            raw = reader.read(13)
            dimensions(result, *struct.unpack(">II", raw[:8]))
        elif name == b"eXIf":
            _exif_bytes(reader.read(size), result)
        elif name == b"tEXt" and size <= 1024:
            raw = reader.read(size)
            key, _, value = raw.partition(b"\x00")
            if key == b"Software" and clean(value):
                result.exif_tags["Software"] = clean(value)
        elif name in (b"IDAT", b"IEND"):
            break
        reader.seek(start + size + 4)


def _webp(reader, result):
    reader.seek(12)
    for _ in range(128):
        header = reader.read(8)
        if len(header) < 8:
            break
        name, size = struct.unpack("<4sI", header)
        start = reader.tell()
        if start + size > reader.size:
            break
        if name == b"VP8X" and size >= 10:
            raw = reader.read(10)
            dimensions(result, int.from_bytes(raw[4:7], "little") + 1, int.from_bytes(raw[7:10], "little") + 1)
        elif name == b"VP8L" and size >= 5:
            raw = reader.read(5)
            if raw[0] == 0x2F:
                value = int.from_bytes(raw[1:5], "little")
                dimensions(result, (value & 0x3FFF) + 1, ((value >> 14) & 0x3FFF) + 1)
        elif name == b"VP8 " and size >= 10:
            raw = reader.read(10)
            if raw[3:6] == b"\x9d\x01\x2a":
                width, height = struct.unpack("<HH", raw[6:10])
                dimensions(result, width & 0x3FFF, height & 0x3FFF)
        elif name == b"EXIF":
            _exif_bytes(reader.read(size), result)
        reader.seek(start + size + (size & 1))


def _svg(reader, result):
    reader.seek(0)
    parser = ET.XMLPullParser(events=("start",))
    previous = b""
    while reader.tell() < reader.size:
        chunk = reader.read(min(4096, reader.size - reader.tell()))
        probe = previous + chunk.replace(b"\x00", b"").upper()
        if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
            raise ValueError("SVG DTDs are not supported")
        previous = probe[-32:]
        parser.feed(chunk)
        for _, root in parser.read_events():
            if root.tag.rsplit("}", 1)[-1] != "svg":
                return
            values = []
            for name in ("width", "height"):
                match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(?:px)?\s*", root.get(name, ""))
                values.append(float(match[1]) if match else 0)
            if not all(values):
                viewbox = root.get("viewBox", "").replace(",", " ").split()
                if len(viewbox) == 4:
                    values = [float(viewbox[2]), float(viewbox[3])]
            dimensions(result, *values)
            return


class ImageExtractor(BinaryExtractor):
    SUPPORTED_EXTENSIONS = frozenset([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".svg"])
    MIME_TYPES = frozenset(["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/x-ms-bmp", "image/tiff", "image/svg+xml"])

    def _inspect(self, reader, result):
        head = reader.read(16)
        kind = None
        if head.startswith(b"\xff\xd8"):
            kind = "JPEG"
            _jpeg(reader, result)
        elif head.startswith(b"\x89PNG\r\n\x1a\n"):
            kind = "PNG"
            _png(reader, result)
        elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            kind = "WEBP"
            _webp(reader, result)
        elif head.startswith((b"GIF87a", b"GIF89a")) and len(head) >= 10:
            kind = "GIF"
            dimensions(result, *struct.unpack("<HH", head[6:10]))
        elif head.startswith(b"BM"):
            kind = "BMP"
            reader.seek(14)
            raw = reader.read(12)
            if len(raw) == 12:
                dib = int.from_bytes(raw[:4], "little")
                if dib == 12:
                    dimensions(result, *struct.unpack("<HH", raw[4:8]))
                elif dib >= 40:
                    width, height = struct.unpack("<ii", raw[4:12])
                    dimensions(result, width, abs(height))
        elif head.startswith((b"II*\x00", b"MM\x00*")):
            kind = "TIFF"
            _tiff(reader, result, reader.size)
        elif reader.name.lower().endswith(".svg") or head.lstrip().startswith(b"<"):
            kind = "SVG"
            _svg(reader, result)
        else:
            result.extraction_status = "PARTIAL"
            result.error_message = "Unrecognized image header"
            return

        try:
            from PIL import Image
        except ImportError:
            result.extraction_status = "PARTIAL"
            result.error_message = "Pillow unavailable; native header metadata only"
        else:
            # Pillow's WebP opener reads the full compressed file. SVG has no
            # Pillow parser. Keep these on the native header-only path.
            if kind not in ("WEBP", "SVG"):
                reader.seek(0)
                try:
                    with Image.open(reader, formats=[kind]) as image:
                        dimensions(result, *image.size)
                        # PNG.getexif() calls load() when no EXIF chunk exists.
                        exif = image.getexif() if kind != "PNG" or "exif" in image.info else {}
                        for tag, name in _EXIF_FIELDS.items():
                            value = clean(exif.get(tag))
                            if value:
                                result.exif_tags[name] = value
                        if 34665 in exif and hasattr(exif, "get_ifd"):
                            sub = exif.get_ifd(34665)
                            for tag, name in _EXIF_FIELDS.items():
                                value = clean(sub.get(tag))
                                if value:
                                    result.exif_tags[name] = value
                except (HeaderLimit, TimeoutError):
                    raise
                except Exception:
                    result.extraction_status = "PARTIAL"
                    result.error_message = "Image backend could not read all header metadata"
        if not result.dimensions:
            result.extraction_status = "PARTIAL"
            result.error_message = "Image dimensions could not be recovered"
    def _finalize(self, result):
        result.created_date = result.exif_tags.get("DateTimeOriginal") or result.exif_tags.get("DateTime")
        keyword(result, result.exif_tags.get("Software"))
